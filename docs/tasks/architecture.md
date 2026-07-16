# Task Execution System Architecture

## Overview

The task execution system is a **deterministic, resumable, auditable** framework for decomposing a high-level goal into concrete tasks and executing them reliably via LLM agents. It provides:

1. **DAG-based planning** — LLM produces a valid dependency graph (architecture → schema → config → core → tests → integration)
2. **Human-in-the-loop approval** — Rich CLI approval loop with modify/reject options
3. **Atomic persistence** — SQLite WAL-mode DB with crash-safe state transitions
4. **Automatic crash recovery** — Orphaned `IN_PROGRESS` tasks auto-recovered on restart
5. **LLM-as-judge evaluation** — Each task output scored against acceptance criteria
6. **Structured observability** — Progress tables, structured logs, final summary

---

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        /plan <goal>                              │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                    planner.create_plan()                         │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ LLM (structured output) → ExecutionPlan                 │    │
│  │   - project_name, goal_summary, tech_stack              │    │
│  │   - tasks[5-20]: id, title, desc, type, deps, files    │    │
│  │   - risks[], assumptions[]                              │    │
│  └─────────────────────────────────────────────────────────┘    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│                 approval.present_plan_for_approval()            │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Rich Table: ID | Type | Title | Deps | Output Files     │    │
│  │ [A]pprove  [M]odify task  [R]eject → re-plan            │    │
│  └─────────────────────────────────────────────────────────┘    │
└──────────────────────────┬──────────────────────────────────────┘
                           │ Approved
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│              task_store.SQLiteTaskStore.create_project()        │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ INSERT INTO projects (id, name, goal, plan_json, ...)   │    │
│  │ INSERT INTO tasks (id, project_id, title, desc, ...)    │    │
│  │   x N tasks                                             │    │
│  └─────────────────────────────────────────────────────────┘    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
                           ▼
        ┌───────────────────────────────────────┐
        │     recovery.RecoveryManager.recover() │  (auto on /plan if existing project)
        │  ┌─────────────────────────────────┐   │
        │  │ SELECT * FROM tasks             │   │
        │  │ WHERE status='in_progress'      │   │
        │  │ FOR EACH:                       │   │
        │  │   if retry_count < max_retries  │   │
        │  │     UPDATE status='pending'     │   │
        │  │   else                          │   │
        │  │     UPDATE status='failed'      │   │
        │  └─────────────────────────────────┘   │
        └──────────────────────────┬──────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────┐
│              orchestrator.TaskOrchestrator.run()                │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ while True:                                             │    │
│  │   progress = store.get_progress(project_id)             │    │
│  │   if pending==0 and in_progress==0: break               │    │
│  │                                                         │    │
│  │   ready = store.get_ready_tasks(project_id)             │    │
│  │   # pending tasks where ALL deps are completed/skipped  │    │
│  │                                                         │    │
│  │   if not ready:                                         │    │
│  │     if in_progress > 0: await asyncio.sleep(5)          │    │
│  │     else: break  # blocked by failed deps               │    │
│  │                                                         │    │
│  │   batch = ready[:max_concurrent]                        │    │
│  │   await asyncio.gather(*[_execute(t) for t in batch])   │    │
│  └─────────────────────────────────────────────────────────┘    │
└──────────────────────────┬──────────────────────────────────────┘
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
    │ executor.   │ │ executor.   │ │ executor.   │
    │ run_subtask │ │ run_subtask │ │ run_subtask │
    │ _agent()    │ │ _agent()    │ │ _agent()    │
    └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
           │               │               │
           ▼               ▼               ▼
    ┌─────────────────────────────────────────────┐
    │  Fresh LangGraph agent per task             │
    │  - Tools selected by task_type              │
    │  - System prompt: task + deps + criteria    │
    │  - Writes ALL files to disk                 │
    │  - Returns summary                          │
    └────────────────────┬────────────────────────┘
                         │
                         ▼
    ┌─────────────────────────────────────────────┐
    │  _judge_task() — LLM-as-Judge               │
    │  - Scores output 0-10 vs criteria           │
    │  - passed = score >= 6                      │
    │  - FAIL → ValueError → retry logic          │
    └────────────────────┬────────────────────────┘
                         │
           ┌─────────────┴─────────────┐
           ▼                           ▼
    ┌─────────────┐             ┌─────────────┐
    │ store.      │             │ store.      │
    │ complete_   │             │ fail_task() │
    │ task()      │             │ (retries++) │
    └─────────────┘             └─────────────┘
```

---

## Module Responsibilities

| File | Responsibility | Key Exports |
|------|---------------|-------------|
| `planner.py` | LLM-structured planning | `create_plan(goal, ctx) → ExecutionPlan` |
| `approval.py` | Human approval UI | `present_plan_for_approval(plan) → ExecutionPlan \| None` |
| `task_store.py` | SQLite persistence + state machine | `SQLiteTaskStore`, `Task`, `TaskStatus`, `TaskType` |
| `recovery.py` | Crash recovery | `RecoveryManager.recover(project_id) → int` |
| `orchestrator.py` | Main execution loop | `TaskOrchestrator.run(project_id)` |
| `executor.py` | Per-task agent + judge | `run_subtask_agent(task, dep_outputs) → str` |
| `status.py` | `/task_status` CLI | `show_task_status(project_id)` |
| `__init__.py` | Public API exports | `handle_plan_command`, `show_task_status` |

---

## State Machine

```
                    ┌─────────────────┐
                    │     PENDING     │
                    └────────┬────────┘
                             │ claim_task()
                             ▼
                    ┌─────────────────┐
                    │  IN_PROGRESS    │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
         complete_task()  fail_task()    (crash)
              │              │              │
              ▼              ▼              ▼
    ┌───────────────┐ ┌───────────┐ ┌───────────────┐
    │   COMPLETED   │ │  PENDING  │ │  IN_PROGRESS  │ (on restart)
    │  (terminal)   │ │(retry ++) │ │  (orphaned)   │
    └───────────────┘ └─────┬─────┘ └───────┬───────┘
                            │                │
                       max_retries         recovery
                            │                │
                            ▼                ▼
                     ┌───────────┐    ┌───────────┐
                     │   FAILED  │    │  PENDING  │
                     │ (terminal)│    │(retry ++) │
                     └───────────┘    └─────┬─────┘
                                            │
                                       max_retries
                                            │
                                            ▼
                                     ┌───────────┐
                                     │   FAILED  │
                                     │ (terminal)│
                                     └───────────┘
```

**Terminal states:** `COMPLETED`, `FAILED`, `SKIPPED`, `BLOCKED`

---

## Database Schema

### `projects` table
| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | UUID |
| `name` | TEXT | Project name (from plan) |
| `goal` | TEXT | User's original goal |
| `plan_json` | TEXT | Full `ExecutionPlan` JSON |
| `status` | TEXT | `planning` \| `approved` \| `running` \| `completed` \| `failed` |
| `created_at` | REAL | Unix epoch |
| `approved_at` | REAL | Unix epoch (when approved) |

### `tasks` table
| Column | Type | Description |
|--------|------|-------------|
| `id` | TEXT PK | `task_001`, `task_002`, ... |
| `project_id` | TEXT FK | → projects.id |
| `title` | TEXT | Human-readable title |
| `description` | TEXT | Detailed instructions for agent |
| `task_type` | TEXT | `design`\|`implement`\|`test`\|`review`\|`integrate`\|`configure` |
| `status` | TEXT | Current state (see state machine) |
| `depends_on` | TEXT | JSON array of task IDs |
| `output_files` | TEXT | JSON array of file paths |
| `acceptance_criteria` | TEXT | JSON array of criteria strings |
| `result` | TEXT | Agent summary on success |
| `error` | TEXT | Error message on failure |
| `retry_count` | INTEGER | 0 to max_retries |
| `max_retries` | INTEGER | Default 3 (configurable) |
| `execution_order` | INTEGER | Display order from plan |
| `created_at` | REAL | Unix epoch |
| `started_at` | REAL | When claimed |
| `completed_at` | REAL | When completed/failed |

**Indexes:**
- `idx_tasks_project (project_id, status)` — for `get_ready_tasks` and `get_progress`

---

## Task Type → Tool Mapping

| Task Type | Tools | Use Case |
|-----------|-------|----------|
| `design` | `read_file`, `write_file`, `list_directory` | Architecture, schemas, API contracts |
| `implement` | `read_file`, `write_file`, `append_file`, `list_directory` | Core implementation |
| `test` | `read_file`, `write_file`, `append_file`, `list_directory`, `run_command` | Unit/integration tests |
| `review` | `read_file`, `write_file` | Code review, linting |
| `integrate` | `read_file`, `write_file`, `append_file`, `list_directory`, `run_command` | Wiring, e2e tests |
| `configure` | `read_file`, `write_file`, `list_directory`, `file_exists` | Config, CI/CD, env |

---

## LLM-as-Judge

### Judge Prompt
```
You are a code review judge. Given a task description, its acceptance criteria,
and the AI agent's output, decide whether the task was completed satisfactorily.

Score 0-10:
 8-10 → passed (all acceptance criteria met)
 5-7  → borderline (minor gaps, still usable)
 0-4  → failed (criteria not met, re-execution needed)

Set passed=true if score >= 6. One short sentence for reason.
```

### Scoring Threshold
- `score >= 8` → **passed** (all criteria met)
- `score 5-7` → **borderline** (minor gaps, counts as passed)
- `score <= 4` → **failed** (re-execution triggered)

### Retry Flow
```
Judge score < 6
       │
       ▼
ValueError raised
       │
       ▼
orchestrator._execute() catches
       │
       ▼
store.fail_task() → retry_count++
       │
       ├── retry_count < max_retries → status=PENDING (re-queue)
       │
       └── retry_count >= max_retries → status=FAILED
```

---

## Configuration

`config.yaml`:
```yaml
tasks:
  db_path: ".educosys/tasks.db"
  max_concurrent: 1          # parallel task execution
  default_max_retries: 3     # per-task retry limit
  judge_model: ""            # empty = use main model; set to cheaper model for judge
```

---

## Extensibility Points

| Extension | Location | How |
|-----------|----------|-----|
| New task type | `task_store.py:TaskType`, `executor.py:_TOOLS_BY_TYPE` | Add enum + tool list |
| Custom planner prompt | `planner.py:_SYSTEM_PROMPT` | Edit system prompt |
| Custom judge criteria | `executor.py:_JUDGE_SYSTEM_PROMPT`, `_JudgeVerdict` | Adjust scoring |
| Parallel execution | `orchestrator.py:TaskOrchestrator(max_concurrent=N)` | Set >1 |
| Custom recovery | `recovery.py:RecoveryManager.recover()` | Override logic |
| New CLI command | `__init__.py`, `main.py` command router | Add handler |