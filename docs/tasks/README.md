# Tasks System Documentation

Complete documentation for the **long-running task execution framework** powering the `/plan` command.

---

## Quick Start

```bash
# Start a new project
/plan "Build a REST API for todo items with CRUD operations"

# Check progress
/task_status

# Manual recovery (if needed)
/task_recover <project_id>
```

---

## Documentation Index

| Document | Description |
|----------|-------------|
| [architecture.md](architecture.md) | System overview, component diagram, state machine, DB schema |
| [planner.md](planner.md) | LLM-structured planning, ExecutionPlan schema, DAG constraints |
| [approval.md](approval.md) | Human-in-the-loop approval UI (Approve/Modify/Reject) |
| [task_store.md](task_store.md) | SQLite persistence, atomic transitions, queries |
| [orchestrator.md](orchestrator.md) | Main execution loop, concurrency, retry integration |
| [executor.md](executor.md) | Per-task agent + LLM-as-judge, tool policy, judge threshold |
| [recovery.md](recovery.md) | Crash recovery: detects orphaned IN_PROGRESS, resets with retries |
| [status.md](status.md) | `/task_status` CLI — Rich table of project tasks |

---

## Core Concepts

### Execution Plan (from Planner)
- 5–20 tasks with stable IDs (`task_001`...)
- DAG dependencies (`depends_on`)
- Explicit output files + acceptance criteria
- Task type determines tool set

### Human Approval
- Rich table preview
- `[A]pprove` / `[M]odify task` / `[R]eject`
- Loop until approve or reject

### Atomic Persistence (SQLite WAL)
- Projects + Tasks tables
- Single `UPDATE` per state transition
- Write before act (claim → write → execute)
- Crash-safe, concurrent reads

### Crash Recovery (No Heartbeat)
- Single-process serial → at most 1 `IN_PROGRESS`
- On restart: any `IN_PROGRESS` = crashed
- Reset to `PENDING` (retry++) or `FAILED` (exhausted)

### Orchestration Loop
```
ready tasks → claim → agent + judge → complete/fail → repeat
```

### LLM-as-Judge
- Scores output 0–10 vs acceptance criteria
- `score >= 6` → passed
- `score < 6` → `ValueError` → retry

---

## Configuration (`config.yaml`)

```yaml
tasks:
  db_path: ".educosys/tasks.db"
  max_concurrent: 1          # serial by default
  default_max_retries: 3

llm:
  provider: "anthropic"
  model: "claude-3-5-sonnet-20241022"
  judge_model: ""            # empty = use main model; set to cheaper model
```

---

## Task Types & Tools

| Type | Tools | Typical Outputs |
|------|-------|-----------------|
| `design` | read, write, list | specs, schemas, diagrams |
| `configure` | read, write, list, exists | config files, CI/CD, env |
| `implement` | read, write, append, list | source code |
| `test` | read, write, append, list, run | test files, run commands |
| `review` | read, write | review docs, lint configs |
| `integrate` | read, write, append, list, run | e2e tests, docker, README |

---

## Extending the System

| Extension | Files to Modify |
|-----------|-----------------|
| New task type | `task_store.py` (enum), `executor.py` (tools), `planner.py` (prompt) |
| Custom planner rules | `planner.py:_SYSTEM_PROMPT` |
| Custom judge criteria | `executor.py:_JUDGE_SYSTEM_PROMPT`, `_JudgeVerdict` |
| Parallel execution | `orchestrator.py:TaskOrchestrator(max_concurrent=N)` |
| Custom recovery | `recovery.py:RecoveryManager.recover()` |
| New CLI command | `__init__.py`, `main.py` router |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Tasks stuck `IN_PROGRESS` on restart | Previous crash mid-task | Auto-recovery runs on `/plan`; or `/task_recover` |
| Judge rejects valid output | Criteria too strict/vague | Tune `acceptance_criteria` in planner prompt or judge prompt |
| Tasks run out of order | Missing `depends_on` / cycle | Fix DAG in planner output |
| DB locked | Multiple processes | Ensure single process; WAL handles readers |
| "No ready tasks" but pending exist | Blocked by failed dependency | Check `/task_status` for failed tasks |
| Empty agent output | Agent didn't write files | Check tool access; increase `max_tokens` |

---

## File Layout

```
educosys_claude/
├── tasks/
│   ├── __init__.py          # handle_plan_command, show_task_status
│   ├── planner.py           # create_plan() → ExecutionPlan
│   ├── approval.py          # present_plan_for_approval()
│   ├── task_store.py        # SQLiteTaskStore + enums + Task
│   ├── recovery.py          # RecoveryManager.recover()
│   ├── orchestrator.py      # TaskOrchestrator.run()
│   ├── executor.py          # run_subtask_agent() + judge
│   └── status.py            # show_task_status()
└── docs/tasks/
    ├── architecture.md      # this folder
    ├── planner.md
    ├── approval.md
    ├── task_store.md
    ├── orchestrator.md
    ├── executor.md
    ├── recovery.md
    └── status.md
```