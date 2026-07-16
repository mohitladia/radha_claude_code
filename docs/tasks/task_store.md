# Task Store Module

## Purpose

Authoritative **SQLite persistence layer** for all task state. Implements atomic state transitions, crash-safe WAL mode, and dependency-aware queries.

## Key Classes

```python
# task_store.py
class TaskStatus(str, Enum):
    PENDING     = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED   = "completed"
    FAILED      = "failed"
    BLOCKED     = "blocked"
    SKIPPED     = "skipped"

class TaskType(str, Enum):
    DESIGN    = "design"
    IMPLEMENT = "implement"
    TEST      = "test"
    REVIEW    = "review"
    INTEGRATE = "integrate"
    CONFIGURE = "configure"

@dataclass
class Task:
    id: str
    project_id: str
    title: str
    description: str
    task_type: str
    status: str = TaskStatus.PENDING
    depends_on: str = "[]"           # JSON list
    output_files: str = "[]"         # JSON list
    acceptance_criteria: str = "[]"  # JSON list
    result: str | None = None
    error: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    execution_order: int = 0
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
```

## SQLiteTaskStore

### Initialization

```python
store = SQLiteTaskStore(db_path=".educosys/tasks.db")
# Creates directory, enables WAL + foreign keys
```

### Project Operations

```python
# Create project + tasks from approved plan
project_id = store.create_project(goal, plan)
# Returns UUID, inserts into projects + tasks tables

# Get latest approved project (for resume)
project_id = store.get_latest_approved_project()
# Returns str | None
```

### Atomic State Transitions

All transitions are single `UPDATE` statements — **write before act**.

```python
# PENDING → IN_PROGRESS (atomic claim)
success = store.claim_task(task_id)
# Returns True if claim succeeded, False if already claimed

# IN_PROGRESS → COMPLETED
store.complete_task(task_id, result_summary)

# IN_PROGRESS → PENDING (retry) OR → FAILED (exhausted)
store.fail_task(task_id, error_message)
# Internal SQL CASE:
#   WHEN retry_count + 1 < max_retries THEN 'pending'
#   ELSE 'failed'

# Any → BLOCKED (dependency failed)
store.block_task(task_id, reason)
```

### Queries

```python
# Tasks ready to run: PENDING + all deps COMPLETED/SKIPPED
ready_tasks = store.get_ready_tasks(project_id)
# Returns list[dict] ordered by execution_order

# All tasks for project
all_tasks = store.get_all_tasks(project_id)

# Progress counts by status
progress = store.get_progress(project_id)
# {"pending": 5, "in_progress": 1, "completed": 12, "failed": 0, "blocked": 2, "skipped": 0}

# Dependency results for agent context injection
dep_outputs = store.get_dep_results(dep_ids)
# [{"id": "task_001", "title": "...", "result": "..."}, ...]
```

## Database Details

### WAL Mode
```python
conn.execute("PRAGMA journal_mode=WAL")     # Crash-safe, concurrent reads
conn.execute("PRAGMA foreign_keys=ON")      # Referential integrity
```

### Connection Pattern
```python
@contextmanager
def _conn(self):
    conn = sqlite3.connect(self.db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```
**Per-operation connection** — no shared connection, thread-safe by design.

## State Transition SQL

### Claim Task (PENDING → IN_PROGRESS)
```sql
UPDATE tasks
SET status = 'in_progress', started_at = unixepoch()
WHERE id = ? AND status = 'pending'
```
Returns `rowcount == 1` — prevents double-claim.

### Complete Task (IN_PROGRESS → COMPLETED)
```sql
UPDATE tasks
SET status = 'completed', result = ?, completed_at = unixepoch()
WHERE id = ?
```

### Fail Task (IN_PROGRESS → PENDING/FAILED)
```sql
UPDATE tasks
SET retry_count = retry_count + 1,
    error = ?,
    status = CASE
        WHEN retry_count + 1 < max_retries THEN 'pending'
        ELSE 'failed'
    END,
    started_at = NULL
WHERE id = ?
```

### Block Task (ANY → BLOCKED)
```sql
UPDATE tasks
SET status = 'blocked', error = ?
WHERE id = ?
```

## Ready Task Query

```sql
-- Get all PENDING tasks for project (ordered)
SELECT * FROM tasks
WHERE project_id = ? AND status = 'pending'
ORDER BY execution_order

-- In Python: filter where all deps are COMPLETED/SKIPPED
-- _all_deps_done() checks per-task:
SELECT COUNT(*) FROM tasks
WHERE id IN (?,?,...) AND status NOT IN ('completed', 'skipped')
-- Returns 0 → all deps done
```

## Recovery Scenario

On process restart, any task with `status='in_progress'` is **orphaned**:

```python
# recovery.py:RecoveryManager.recover()
crashed = conn.execute(
    "SELECT id, title, retry_count, max_retries "
    "FROM tasks WHERE project_id = ? AND status = 'in_progress'",
    (project_id,)
).fetchall()

for task in crashed:
    if task["retry_count"] < task["max_retries"]:
        # Reset to PENDING, increment retry
        UPDATE tasks SET status='pending', started_at=NULL,
               retry_count=retry_count+1,
               error='CRASH: process died mid-execution'
        WHERE id = ?
    else:
        # Mark FAILED
        UPDATE tasks SET status='failed',
               error='CRASH: max retries exceeded after repeated crashes'
        WHERE id = ?
```

## Configuration

```yaml
tasks:
  db_path: ".educosys/tasks.db"
  default_max_retries: 3
```

## Adding Fields

To add a new column:
1. Add to `Task` dataclass
2. Update `create_project()` INSERT
3. Add migration in `_setup_db()` (ALTER TABLE)
4. Update `_all_deps_done()` if dependency-related