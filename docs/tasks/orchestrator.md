# Orchestrator Module — Main Execution Loop

## Purpose

`TaskOrchestrator.run(project_id)` — drives the execution loop until all tasks reach terminal state.

---

## Algorithm

```python
async def run(self, project_id: str) -> None:
    while True:
        # 1. Check progress
        progress = self.store.get_progress(project_id)
        pending = progress.get("pending", 0)
        in_progress = progress.get("in_progress", 0)
        completed = progress.get("completed", 0)
        failed = progress.get("failed", 0)
        total = sum(progress.values())
        
        console.print(f"Progress: {completed}/{total} completed · "
                      f"{in_progress} in-progress · {pending} pending · {failed} failed")
        
        # 2. All done?
        if pending == 0 and in_progress == 0:
            _print_final_summary(progress)
            break
        
        # 3. Get ready tasks (PENDING + all deps done)
        ready = self.store.get_ready_tasks(project_id)
        
        if not ready:
            if in_progress > 0:
                console.print("[dim]⏳ Waiting for in-progress tasks...[/dim]")
                await asyncio.sleep(5)
                continue
            else:
                # Nothing ready, nothing running → blocked by failed deps
                console.print("[yellow]⚠ No ready tasks — some may be blocked by failed dependencies.[/yellow]")
                console.print("[yellow]  Use /task_status to inspect.[/yellow]")
                break
        
        # 4. Dispatch batch (respect max_concurrent)
        batch = ready[:self.max_concurrent]
        await asyncio.gather(*[self._execute(task) for task in batch])
```

---

## Task Execution (`_execute`)

```python
async def _execute(self, task: dict) -> None:
    console.print(f"\n[bold]▶ Starting:[/bold] [{task['id']}] {task['title']}")
    
    # Atomic claim (prevents double-execution if called concurrently)
    if not self.store.claim_task(task["id"]):
        console.print(f"[dim]⚠ Task {task['id']} already claimed — skipping[/dim]")
        return
    
    try:
        # Fetch dependency outputs for context injection
        dep_ids = json.loads(task.get("depends_on") or "[]")
        dep_outputs = self.store.get_dep_results(dep_ids)
        
        # Run agent + judge
        result = await run_subtask_agent(task, dep_outputs=dep_outputs)
        
        # Store success
        self.store.complete_task(task["id"], result)
        console.print(f"[green]✅ Completed:[/green] [{task['id']}] {task['title']}")
    
    except Exception as e:
        error_msg = str(e)
        self.store.fail_task(task["id"], error_msg)
        console.print(f"[red]❌ Failed:[/red]    [{task['id']}] {task['title']}: {error_msg[:120]}")
        logger.error(f"Task {task['id']} failed: {error_msg}")
```

---

## Concurrency Control

```python
# orchestrator.py
class TaskOrchestrator:
    def __init__(self, store: SQLiteTaskStore, max_concurrent: int = 1):
        self.store = store
        self.max_concurrent = max_concurrent  # default 1 = serial
```

**Serial (`max_concurrent=1`)** — default, safest, predictable costs, no race conditions.

**Parallel (`max_concurrent=N`)** — up to N tasks run simultaneously.
- Requires: independent tasks (no shared files), idempotent operations
- Risk: DB contention, judge contention, file conflicts

---

## Full Flow: `handle_plan_command()`

```python
async def handle_plan_command(goal: str) -> None:
    # 1. Setup
    db_path = config.get("tasks", {}).get("db_path", ".educosys/tasks.db")
    store = SQLiteTaskStore(db_path)
    recovery = RecoveryManager(store)
    
    # 2. Resume or fresh plan
    project_id = store.get_latest_approved_project()
    if project_id:
        console.print(f"\n[yellow]↩ Resuming existing project {project_id}...[/yellow]")
        recovered = recovery.recover(project_id)
        if recovered:
            console.print(f"[dim]Recovered {recovered} crashed task(s)[/dim]")
    else:
        # Planning + approval loop
        console.print("\n[dim]Planning with LLM...[/dim]")
        extra_context = ""
        approved_plan = None
        
        while approved_plan is None:
            raw_plan = create_plan(goal, extra_context)
            approved_plan = present_plan_for_approval(raw_plan)
            if approved_plan is None:
                extra_context = input("What should change in the re-plan?\n> ").strip()
                console.print("\n[dim]Re-planning with your feedback...[/dim]")
        
        # 3. Persist
        project_id = store.create_project(goal, approved_plan)
        console.print(f"\n[dim]Project {project_id} saved.[/dim]")
    
    # 4. Execute
    orchestrator = TaskOrchestrator(store, max_concurrent=1)
    await orchestrator.run(project_id)
    
    # 5. Re-index for /ask
    console.print("\n[dim]Re-indexing generated files for /ask...[/dim]")
    try:
        get_indexer()(str(Path.cwd()))
        console.print("[green]✓ Index updated — you can now use /ask about generated code.[/green]")
    except Exception as e:
        logger.warning(f"Re-index failed: {e}")
        console.print(f"[yellow]⚠ Re-index failed: {e}[/yellow]")
```

---

## Progress Display

```
Progress: 3/10 completed · 1 in-progress · 5 pending · 1 failed

▶ Starting: [task_004] Implement User model
✅ Completed: [task_004] Implement User model

Progress: 4/10 completed · 0 in-progress · 5 pending · 1 failed

▶ Starting: [task_005] Create auth routes
❌ Failed:    [task_005] Create auth routes: Judge rejected (score=4): Missing JWT validation
```

---

## Final Summary

```python
def _print_final_summary(progress: dict):
    completed = progress.get("completed", 0)
    failed = progress.get("failed", 0)
    blocked = progress.get("blocked", 0)
    skipped = progress.get("skipped", 0)
    
    if failed == 0 and blocked == 0:
        console.print(f"\n[bold green]🎉 All {completed} tasks completed successfully![/bold green]")
    else:
        console.print(f"\n[bold yellow]⚠ Execution finished with issues:[/bold yellow]")
        console.print(f"  ✅ Completed: {completed}")
        if failed:
            console.print(f"  ❌ Failed:    {failed}  (run /task_status to review)")
        if blocked:
            console.print(f"  🚫 Blocked:   {blocked}  (dependencies failed)")
        if skipped:
            console.print(f"  ⏭ Skipped:   {skipped}")
```

---

## Configuration

```yaml
tasks:
  max_concurrent: 1      # 1 = serial (default)
```

---

## Error Handling Matrix

| Error Source | Caught By | Result |
|--------------|-----------|--------|
| `claim_task` returns False | `_execute` | Skip (already claimed) |
| `run_subtask_agent` → empty output | `_execute` | `fail_task` → retry |
| `run_subtask_agent` → judge fail | `_execute` | `fail_task` → retry |
| Tool exception (write_file, etc.) | `_execute` | `fail_task` → retry |
| DB error (lock, disk full) | `_execute` / `run` | Propagate → process crash → recovery next run |

---

## Extending the Orchestrator

| Feature | Change |
|---------|--------|
| Priority queue | Sort `ready` by `execution_order` or custom priority |
| Async progress hook | Add `on_task_complete(task, result)` callback |
| Cost tracking | Accumulate token usage in `run_subtask_agent` return |
| Pause/resume | Add `project.status = 'paused'`, check in loop |
| Webhook notifications | Call HTTP in `_execute` after complete/fail |