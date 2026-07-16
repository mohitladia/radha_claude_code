# Recovery Module — Crash Recovery

## Purpose

`RecoveryManager.recover(project_id)` — **auto-run at `/plan` startup** — detects and resets tasks left in `IN_PROGRESS` from a crashed process.

---

## Why Recovery Works (No Heartbeat Needed)

**Single-process, serial execution** → at any moment, **at most one task** is `IN_PROGRESS`.

If process dies:
- That one task is the only orphan
- No other process could have claimed it
- On restart, any `IN_PROGRESS` task = definitely crashed

**No timer, no heartbeat, no distributed coordination needed.**

---

## Recovery Algorithm

```python
def recover(self, project_id: str) -> int:
    with self.store._conn() as conn:
        # Find all tasks still marked in_progress
        crashed = conn.execute(
            """SELECT id, title, retry_count, max_retries
               FROM tasks
               WHERE project_id = ? AND status = 'in_progress'""",
            (project_id,)
        ).fetchall()
        
        for task in crashed:
            if task["retry_count"] < task["max_retries"]:
                # Reset to PENDING, increment retry count
                conn.execute(
                    """UPDATE tasks
                       SET status      = 'pending',
                           started_at  = NULL,
                           retry_count = retry_count + 1,
                           error       = 'CRASH: process died mid-execution'
                       WHERE id = ?""",
                    (task["id"],)
                )
                console.print(
                    f"[yellow]🔄 Recovered:[/yellow] {task['id']} ({task['title']}) "
                    f"→ PENDING (retry {task['retry_count'] + 1}/{task['max_retries']})"
                )
            else:
                # Retries exhausted → mark FAILED
                conn.execute(
                    """UPDATE tasks
                       SET status = 'failed',
                           error  = 'CRASH: max retries exceeded after repeated crashes'
                       WHERE id = ?""",
                    (task["id"],)
                )
                console.print(f"[red]❌ Max retries exhausted:[/red] {task['id']} → FAILED")
    
    count = len(crashed)
    if count:
        console.print(f"[dim]Recovery complete: {count} task(s) processed.[/dim]\n")
    return count
```

---

## Integration Point

Called automatically in `orchestrator.handle_plan_command()`:

```python
async def handle_plan_command(goal: str) -> None:
    store = SQLiteTaskStore(...)
    recovery = RecoveryManager(store)
    
    project_id = store.get_latest_approved_project()
    if project_id:
        console.print(f"\n[yellow]↩ Resuming existing project {project_id}...[/yellow]")
        recovered = recovery.recover(project_id)
        if recovered:
            console.print(f"[dim]Recovered {recovered} crashed task(s)[/dim]")
    else:
        # fresh plan → no recovery needed
        ...
```

---

## State Transitions on Recovery

| Crashed State | Retries Left | New State | Retry Count | Error Message |
|---------------|--------------|-----------|-------------|---------------|
| `IN_PROGRESS` | Yes (< max) | `PENDING` | +1 | `CRASH: process died mid-execution` |
| `IN_PROGRESS` | No (= max) | `FAILED` | unchanged | `CRASH: max retries exceeded after repeated crashes` |

---

## Recovery CLI

```bash
# Manual recovery (if auto didn't run)
/task_recover <project_id>
```

Implemented in `status.py` (or separate CLI command).

---

## Edge Cases Handled

| Scenario | Behavior |
|----------|----------|
| Multiple crashed tasks | All processed (only possible if `max_concurrent > 1`) |
| Task crashed on last retry | Marked `FAILED`, not re-queued |
| DB locked during recovery | `_conn()` context manager handles contention |
| Recovery runs twice | Idempotent — second run finds no `IN_PROGRESS` tasks |

---

## Testing Recovery

```python
def test_recovery_resets_in_progress():
    store = SQLiteTaskStore(":memory:")
    store.create_project("test", plan)
    
    # Simulate crash mid-task
    task_id = store.get_all_tasks(project_id)[0]["id"]
    store.claim_task(task_id)  # status = in_progress
    
    # Kill process (simulated by not calling complete_task)
    # Start new process:
    recovery = RecoveryManager(store)
    recovered = recovery.recover(project_id)
    
    assert recovered == 1
    task = store.get_all_tasks(project_id)[0]
    assert task["status"] == "pending"
    assert task["retry_count"] == 1
    assert "CRASH" in task["error"]
```

---

## Configuration

```python
RecoveryManager(store)  # No config — uses task.max_retries from DB
```

---

## Limitations

| Limitation | Mitigation |
|------------|------------|
| `max_concurrent > 1` → multiple `IN_PROGRESS` | Recovery handles all; set `max_concurrent=1` for stronger guarantees |
| Task was actually slow, not crashed | Assumption: serial + no heartbeat = any `IN_PROGRESS` at startup = crashed. If tasks can run > 5 min, consider adding a heartbeat timestamp. |
| External side effects (API calls, file writes) not rolled back | Recovery only resets DB state; re-execution may repeat side effects. Design tasks idempotent where possible. |