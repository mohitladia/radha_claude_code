# Approval Module

## Purpose

Human-in-the-loop approval loop for execution plans. Renders plan as Rich table, prompts for **Approve / Modify / Reject**.

## API

```python
from educosys_claude.tasks.approval import present_plan_for_approval

approved_plan = present_plan_for_approval(raw_plan)
# Returns ExecutionPlan if approved, None if rejected
```

## UI Flow

```
┌─────────────────────────────────────────────────────────────┐
│ Plan: Build REST API for Todos                               │
│ Build a REST API for todo items with CRUD operations...      │
│ Stack: FastAPI, SQLAlchemy, Pydantic | Est: 4.5h             │
│                                                              │
│ ┌────┬─────────┬────────────────────┬────────────┬─────────┐ │
│ │ ID │ Type    │ Title              │ Depends on │ Outputs │ │
│ ├────┼─────────┼────────────────────┼────────────┼─────────┤ │
│ │ 001│ design  │ API Schema Design  │ —          │ specs/  │ │
│ │ 002│ implement│ DB Models          │ 001        │ models/ │ │
│ │ 003│ implement│ CRUD Endpoints     │ 002        │ routes/ │ │
│ │ 004│ test    │ Unit Tests         │ 003        │ tests/  │ │
│ │ 005│ integrate│ E2E Tests          │ 004        │ tests/  │ │
│ └────┴─────────┴────────────────────┴────────────┴─────────┘ │
│                                                              │
│ Risks:                                                       │
│   • Database migrations may need manual intervention         │
└─────────────────────────────────────────────────────────────┘

[A]pprove / [M]odify task / [R]eject and re-plan: 
```

## Options

| Key | Action | Behavior |
|-----|--------|----------|
| `A` | Approve | Returns plan unchanged, execution starts |
| `M` | Modify | Prompts for task ID + new description, re-renders |
| `R` | Reject | Returns `None`, orchestrator re-plans with feedback |

## Modify Flow

```
Enter task ID to modify: task_003

Current description:
Implement GET/POST /todos endpoints with pagination

New description: 
Implement GET/POST /todos endpoints with pagination AND filtering by status

[green]Task updated.[/green]

[A]pprove / [M]odify task / [R]eject and re-plan:
```

## Reject Flow

```
[A]pprove / [M]odify task / [R]eject and re-plan: R

What should change in the re-plan?
> Use PostgreSQL instead of SQLite, add database migration task

Re-planning with your feedback...
```

## Implementation Details

- **Loop until terminal** — keeps prompting until A or R
- **Rich Table** — colored, aligned columns with wrapping
- **Input validation** — task ID must exist, non-empty description
- **Graceful fallback** — any other input shows help message

## Integration

Called by `orchestrator.py:handle_plan_command()`:

```python
approved_plan = None
extra_context = ""

while approved_plan is None:
    raw_plan = create_plan(goal, extra_context)
    approved_plan = present_plan_for_approval(raw_plan)
    if approved_plan is None:
        extra_context = input("What should change in the re-plan?\n> ").strip()
```

## Customization

Add columns to `_render_plan()`:
- `estimated_minutes`
- `risk_level` 
- `assignee` (for team workflows)