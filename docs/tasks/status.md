# Task Status CLI — `/task_status` Command

## Purpose

Rich table display of all tasks for the latest approved project.

---

## Command

```bash
/task_status
```

---

## Output

```
Project: 7f8a2b1c-4d3e-4f1a-9b2c-5d6e7f8a9b0c
Progress: 4/9 completed

┏━━━━┳━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ #  ┃ ID         ┃ Type    ┃ Title                           ┃ Status    ┃ Retries   ┃ Error                                    ┃
┡━━━━╇━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ 1  │ task_001   │ design  │ API Schema Design                │ [green]completed[/] │ 0/3       │                                          │
│ 2  │ task_002   │ implement│ Database Models                  │ [green]completed[/] │ 0/3       │                                          │
│ 3  │ task_003   │ implement│ CRUD Endpoints                   │ [yellow]in_progress[/] │ 0/3       │                                          │
│ 4  │ task_004   │ test    │ Unit Tests for Models            │ [dim]pending[/]     │ 0/3       │                                          │
│ 5  │ task_005   │ test    │ Integration Tests                │ [dim]pending[/]     │ 0/3       │                                          │
│ 6  │ task_006   │ review  │ Code Review                      │ [dim]pending[/]     │ 0/3       │                                          │
│ 7  │ task_007   │ implement│ JWT Authentication               │ [red]failed[/]      │ 3/3       │ Judge rejected: Missing token refresh    │
│ 8  │ task_008   │ configure│ Dockerfile & CI                  │ [red]blocked[/]     │ 0/3       │ Dependency task_007 failed               │
└────┴────────────┴─────────┴──────────────────────────────────┴───────────┴───────────┴────────────────────────────────────────────┘
```

---

## Status Colors

| Status | Color |
|--------|-------|
| `completed` | green |
| `in_progress` | yellow |
| `pending` | dim |
| `failed` | red |
| `blocked` | red |
| `skipped` | dim |

---

## Columns

| Column | Description |
|--------|-------------|
| `#` | Display order (1-indexed) |
| `ID` | Task ID (`task_001` etc.) |
| `Type` | `design`/`implement`/`test`/`review`/`integrate`/`configure` |
| `Title` | Human-readable title |
| `Status` | Current state (colored) |
| `Retries` | `retry_count/max_retries` |
| `Error` | Truncated error message (60 chars) |

---

## Implementation

```python
def show_task_status() -> None:
    db_path = config.get("tasks", {}).get("db_path", ".educosys/tasks.db")
    store = SQLiteTaskStore(db_path)
    project_id = store.get_latest_approved_project()
    
    if not project_id:
        console.print("[yellow]No active project found. Run /plan <goal> first.[/yellow]")
        return
    
    tasks = store.get_all_tasks(project_id)
    progress = store.get_progress(project_id)
    total = sum(progress.values())
    done = progress.get("completed", 0)
    
    console.print(f"\n[bold]Project:[/bold] {project_id}")
    console.print(f"[dim]Progress: {done}/{total} completed[/dim]\n")
    
    table = Table(show_header=True, header_style="bold")
    table.add_column("#", width=4)
    table.add_column("ID", width=12)
    table.add_column("Type", width=10)
    table.add_column("Title", width=35)
    table.add_column("Status", width=12)
    table.add_column("Retries", width=8)
    table.add_column("Error", width=40)
    
    for i, task in enumerate(tasks, 1):
        style = _STATUS_STYLE.get(task["status"], "")
        error = (task.get("error") or "")[:60]
        table.add_row(
            str(i),
            task["id"],
            task["task_type"],
            task["title"],
            f"[{style}]{task['status']}[/{style}]",
            f"{task['retry_count']}/{task['max_retries']}",
            error,
        )
    
    console.print(table)
```

---

## Integration

In `main.py`:

```python
from educosys_claude.tasks import handle_plan_command, show_task_status

if cmd == "task_status":
    show_task_status()
```

---

## Related Commands

| Command | Function |
|---------|----------|
| `/plan <goal>` | Create new or resume existing project |
| `/task_status` | Show progress table for current project |
| `/task_recover <project_id>` | Manual crash recovery (rarely needed) |

---

## Extending Status Display

Add columns by modifying `show_task_status()`:

```python
# Add execution time
table.add_column("Duration", width=10)
# In loop:
duration = ""
if task.get("started_at") and task.get("completed_at"):
    duration = f"{task['completed_at'] - task['started_at']:.0f}s"
table.add_row(..., duration)
```

```python
# Add output files preview
table.add_column("Outputs", width=30)
# In loop:
outputs = json.loads(task.get("output_files") or "[]")
table.add_row(..., ", ".join(outputs[:3]) + ("..." if len(outputs) > 3 else ""))
```