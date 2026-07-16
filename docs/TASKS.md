# Tasks System Documentation

The `educosys_claude/tasks/` module implements a **long-running task execution framework** for the `/plan` command. It plans, persists, executes, and recovers multi-step AI agent workflows.

---

## Architecture Overview

```
/plan <goal>
   │
   ▼
┌─────────────────────────────────────────────┐
│  1. PLANNER  (planner.py)                   │
│     LLM creates ExecutionPlan (5-20 tasks)  │
│     Each task: id, type, deps, files, criteria
└─────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────┐
│  2. APPROVAL  (approval.py)                 │
│     Rich table → [A]pprove / [M]odify / [R]eject
│     Loop until Approve or Reject
└─────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────┐
│  3. PERSIST   (task_store.py)               │
│     SQLite (WAL mode)                       │
│     Tables: projects, tasks                 │
│     Atomic state transitions                │
└─────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────┐
│  4. RECOVER   (recovery.py)                 │
│     On startup: any IN_PROGRESS → PENDING/FAILED
│     (no heartbeat needed — single process)  │
└─────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────┐
│  5. ORCHESTRATE (orchestrator.py)           │
│     Loop: ready tasks → dispatch agents     │
│     Serial by default (max_concurrent=1)    │
└─────────────────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────────────────┐
│  6. EXECUTE   (executor.py)                 │
│     Fresh LangGraph agent per task          │
│     Reads dep outputs → writes files        │
│     LLM-as-judge verifies acceptance crit.  │
│     Retry on failure (max 3 by default)     │
└─────────────────────────────────────────────┘
```

---

## Module Reference

| File | Responsibility |
|------|----------------|
| `planner.py` | LLM planner → `ExecutionPlan` (Pydantic) |
| `approval.py` | Human-in-the-loop Rich table approval loop |
| `task_store.py` | SQLite persistence, atomic state machine |
| `recovery.py` | Crash recovery: `IN_PROGRESS` → `PENDING`/`FAILED` |
| `orchestrator.py` | Main loop: ready tasks → dispatch agents |
| `executor.py` | Per-task LangGraph agent + LLM judge + retries |
| `status.py` | `/task_status` CLI command (Rich table) |
| `approval.py` | Human-in-the-loop plan approval UI |

---

## Task State Machine

```
PENDING ──(claim)──► IN_PROGRESS ──(success)──► COMPLETED (terminal)
                    │
                    ├──(failure, retries left)──► PENDING
                    ├──(failure, no retries)────► FAILED  (terminal)
                    └──(dependency failed)──────► BLOCKED (terminal)

SKIPPED (terminal — human explicitly skipped)
```

**Key invariants:**
- Single process, serial execution → any `IN_PROGRESS` at startup = orphaned
- Every state transition is a single atomic `UPDATE`
- DB writes **before** acting on new state (claim → write → execute)

---

## Database Schema (`task_store.py`)

```sql
-- projects table: one row per /plan invocation
CREATE TABLE projects (
    id              TEXT PRIMARY KEY,      -- UUID
    goal            TEXT NOT NULL,
    plan_json       TEXT NOT NULL,         -- full ExecutionPlan JSON
    status          TEXT NOT NULL,         -- 'planning' | 'approved' | 'executing' | 'completed' | 'failed'
    created_at      REAL NOT NULL,
    updated_at      REAL NOT NULL
);

-- tasks table: 10-40 rows per project
CREATE TABLE tasks (
    id              TEXT PRIMARY KEY,      -- task_001, task_002...
    project_id      TEXT NOT NULL,
    title           TEXT NOT NULL,
    description     TEXT NOT NULL,
    task_type       TEXT NOT NULL,         -- design|implement|test|review|integrate|configure
    status          TEXT NOT NULL,         -- pending|in_progress|completed|failed|blocked|skipped
    depends_on      TEXT NOT NULL,         -- JSON array of task IDs
    output_files    TEXT NOT NULL,         -- JSON array of file paths
    result          TEXT,                  -- agent output summary on success
    error           TEXT,                  -- error message on failure
    retry_count     INTEGER DEFAULT 0,
    max_retries     INTEGER DEFAULT 3,
    execution_order INTEGER NOT NULL,      -- display order from plan
    created_at      REAL NOT NULL,
    started_at      REAL,
    completed_at    REAL,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);
```

---

## CLI Commands

| Command | Handler | Description |
|---------|---------|-------------|
| `/plan <goal>` | `orchestrator.handle_plan_command` | Full plan → approve → execute flow |
| `/task_status` | `status.show_task_status` | Rich table of current project tasks |
| `/task_recover <project_id>` | `recovery.RecoveryManager.recover` | Manual crash recovery |

---

## Task Types (`TaskType` enum)

| Type | Typical Use |
|------|-------------|
| `design` | Architecture, schema, API contracts |
| `implement` | Core implementation, business logic |
| `test` | Unit/integration tests |
| `review` | Code review, linting, security scan |
| `integrate` | Wiring components, end-to-end tests |
| `configure` | Config files, CI/CD, env setup |

---

## Execution Flow Detail

### 1. Planning (`planner.py:create_plan`)
- LLM (structured output) → `ExecutionPlan` with 5-20 `PlannedTask`
- Each task: stable `task_001` IDs, explicit `depends_on` DAG, `output_files`, `acceptance_criteria`
- System prompt enforces DAG ordering: `design → implement → test → integrate`

### 2. Approval (`approval.py:present_plan_for_approval`)
- Rich table: ID | Type | Title | Depends On | Output Files
- Human: `[A]pprove` (returns plan), `[M]odify` (edit task desc), `[R]eject` (returns `None` → re-plan)

### 3. Persistence (`task_store.py:SQLiteTaskStore`)
- `create_project(goal, plan)` → inserts project + all tasks
- `claim_task(id)` → atomic `UPDATE ... WHERE status='pending'` (prevents double-claim)
- `complete_task(id, result)` / `fail_task(id, error)` → atomic transitions

### 4. Recovery (`recovery.py:RecoveryManager.recover`)
- Runs automatically on `/plan` if existing approved project found
- Scans for `status='in_progress'` tasks
- Retries left → `PENDING` (retry_count++)
- No retries left → `FAILED`

### 5. Orchestration (`orchestrator.py:TaskOrchestrator.run`)
```python
while True:
    progress = store.get_progress(project_id)
    if pending == 0 and in_progress == 0: break
    
    ready = store.get_ready_tasks(project_id)  # all deps completed/skipped
    if not ready:
        if in_progress > 0: await asyncio.sleep(5); continue
        else: break  # blocked by failed deps
    
    batch = ready[:max_concurrent]
    await asyncio.gather(*[self._execute(t) for t in batch])
```

### 6. Execution (`executor.py:run_subtask_agent`)
- Fresh LangGraph `create_agent` per task (tools selected by `task_type`)
- System prompt includes: task description, dep outputs, output file list
- Agent streams → final output captured
- **LLM-as-Judge** (`_judge_task`): scores output 1-10 against `acceptance_criteria`
- Score < 6 → `ValueError` → orchestrator retry logic kicks in

---

## Configuration (`config.yaml`)

```yaml
tasks:
  db_path: ".educosys/tasks.db"
  max_concurrent: 1
  default_max_retries: 3
```

---

## Adding a New Task Type

1. Add to `TaskType` enum in `task_store.py`
2. Add tool set in `executor.py:_TOOLS_BY_TYPE`
3. Add system prompt snippet in `executor.py:_build_system_prompt`
4. (Optional) Update planner system prompt in `planner.py:_SYSTEM_PROMPT`

---

## Extending the System

| Extension Point | File | How |
|-----------------|------|-----|
| New planner prompt | `planner.py:_SYSTEM_PROMPT` | Edit system prompt |
| Custom judge criteria | `executor.py:_JudgeVerdict` / `_judge_task` | Adjust scoring |
| New task tools | `executor.py:_TOOLS_BY_TYPE` | Add tool set per task_type |
| Parallel execution | `orchestrator.py:TaskOrchestrator` | Increase `max_concurrent` |
| Custom recovery | `recovery.py:RecoveryManager.recover` | Override logic |

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---------|--------------|-----|
| Tasks stuck `IN_PROGRESS` on restart | Previous process crashed mid-task | Run `/task_recover <project_id>` or re-run `/plan` (auto-recovers) |
| Judge rejects valid output | Criteria too strict / vague | Tune `acceptance_criteria` in planner prompt or judge prompt |
| Tasks run out of order | `depends_on` missing / cycle | Check planner output DAG validity |
| DB locked | Multiple processes | Ensure single process; WAL mode handles readers |

---

## File Layout

```
educosys_claude/
├── tasks/
│   ├── __init__.py          # exports: handle_plan_command, show_task_status
│   ├── planner.py           # LLM planner → ExecutionPlan
│   ├── approval.py          # Human approval UI
│   ├── task_store.py        # SQLite persistence + Task/TaskStatus/TaskType
│   ├── recovery.py          # Crash recovery
│   ├── orchestrator.py      # Main execution loop
│   ├── executor.py          # Per-task agent + LLM judge
│   └── status.py            # /task_status CLI command
└── TASKS.md                 # this file
```