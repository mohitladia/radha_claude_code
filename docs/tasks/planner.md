# Task Planner — LLM-Structured Planning

## Purpose

`create_plan(goal, extra_context)` → **`ExecutionPlan`** (Pydantic model)

Single LLM call with structured output produces a complete, validated execution plan.

---

## Output Schema

```python
class PlannedTask(BaseModel):
    id: str                      # task_001, task_002...
    title: str
    description: str
    task_type: TaskType          # design|implement|test|review|integrate|configure
    depends_on: list[str]        # valid task IDs in same plan (DAG)
    estimated_minutes: int
    output_files: list[str]      # every file this task writes
    acceptance_criteria: list[str]  # 3-5 verifiable conditions

class ExecutionPlan(BaseModel):
    project_name: str
    goal_summary: str
    tech_stack: list[str]
    total_estimated_hours: float
    tasks: list[PlannedTask]
    risks: list[str]
    assumptions: list[str]
```

---

## Planner System Prompt

```python
_SYSTEM_PROMPT = """You are a senior software architect. Given a software goal, produce a detailed
ExecutionPlan broken into concrete tasks for an AI agent to implement.

Rules:
- 5 to 20 tasks
- Task IDs must be stable snake_case: task_001, task_002, ...
- depends_on must reference valid task IDs in the same plan
- Ordering must form a valid DAG (no cycles): 
  architecture → schema → config → core → tests → integration
- output_files must list every file the task will write to disk
- acceptance_criteria must be concrete and verifiable (3-5 items per task)
- task_type must be one of: design, implement, test, review, integrate, configure
"""
```

---

## Task Type Semantics

| Type | Typical Position | Tools | Outputs |
|------|------------------|-------|---------|
| `design` | 1-2 | read, write, list | ARCHITECTURE.md, API_CONTRACTS.yaml, SCHEMA.sql |
| `configure` | Early | read, write, list, exists | pyproject.toml, .env.example, docker-compose.yml, CI/CD |
| `implement` | Core | read, write, append, list | src/**.py, lib/**.ts, etc. |
| `test` | After implement | read, write, append, list, run | tests/**.py, pytest.ini |
| `review` | Any | read, write | REVIEW_*.md, lint configs |
| `integrate` | Last | read, write, append, list, run | E2E tests, docker-entrypoint, README |

---

## DAG Constraints

The planner **must** produce a valid DAG. Invalid plans are rejected at runtime by `task_store.get_ready_tasks()`.

### Typical Ordering

```
task_001 (design)        → task_002 (design)       → task_003 (configure)
                                                    ↓
task_004 (implement) ← task_005 (implement) ← task_006 (implement)
                                                    ↓
task_007 (test) ← task_008 (test) 
                                                    ↓
task_009 (integrate) ← task_010 (review)
```

### Cycle Prevention

LLM is instructed but **not guaranteed** to avoid cycles. Runtime check in `get_ready_tasks()` will hang if cycles exist — progress stalls at "no ready tasks, in_progress=0".

---

## Acceptance Criteria Guidelines

Good criteria are **verifiable by the judge**:

| ❌ Vague | ✅ Verifiable |
|---------|---------------|
| "Code is clean" | "No lint errors via `ruff check src/`" |
| "Tests pass" | "All tests in `tests/test_auth.py` pass with `pytest -v`" |
| "Config works" | "Running `docker compose up` starts all 3 services without error" |
| "API documented" | "File `docs/api.md` exists with GET/POST /users endpoints" |

**Minimum 3, maximum 5 per task.**

---

## Extra Context (Re-planning)

On rejection (`present_plan_for_approval` returns `None`):

```python
while approved_plan is None:
    raw_plan = create_plan(goal, extra_context)
    approved_plan = present_plan_for_approval(raw_plan)
    if approved_plan is None:
        extra_context = input("What should change in the re-plan?\n> ").strip()
```

User feedback is injected verbatim into next planning call — enables iterative refinement.

---

## Example Plan Output

```json
{
  "project_name": "User Auth API",
  "goal_summary": "REST API for user registration, login, JWT tokens",
  "tech_stack": ["FastAPI", "SQLAlchemy", "PostgreSQL", "Pytest"],
  "total_estimated_hours": 3.5,
  "tasks": [
    {
      "id": "task_001",
      "title": "Design API contracts",
      "description": "Define OpenAPI spec for /auth/register, /auth/login, /auth/me",
      "task_type": "design",
      "depends_on": [],
      "estimated_minutes": 30,
      "output_files": ["docs/openapi.yaml"],
      "acceptance_criteria": [
        "openapi.yaml validates with `openapi-spec-validator`",
        "Contains POST /auth/register with email, password",
        "Contains POST /auth/login returning JWT",
        "Contains GET /auth/me requiring Bearer token"
      ]
    },
    {
      "id": "task_002",
      "title": "Create database models",
      "description": "SQLAlchemy User model with email, hashed_password, is_active",
      "task_type": "implement",
      "depends_on": ["task_001"],
      "estimated_minutes": 25,
      "output_files": ["src/models/user.py"],
      "acceptance_criteria": [
        "User model defines email (unique), hashed_password, is_active columns",
        "Uses bcrypt/passlib for password hashing",
        "Includes __repr__ for debugging"
      ]
    }
  ],
  "risks": ["JWT secret management in production", "Password hashing algorithm choice"],
  "assumptions": ["PostgreSQL available at DATABASE_URL", "Python 3.11+"]
}
```

---

## Configuration

```yaml
llm:
  provider: "anthropic"
  model: "claude-3-5-sonnet-20241022"
  temperature: 0  # deterministic planning
```

---

## Validation

After `create_plan()` returns, orchestrator validates:

1. All `depends_on` IDs exist in `plan.tasks`
2. No duplicate task IDs
3. `output_files` non-empty for implement/test tasks
4. `acceptance_criteria` length 3-5 per task
5. DAG check (implicit — will hang in orchestrator if cyclic)

---

## Extending the Planner

| Change | File |
|--------|------|
| Add task type | `task_store.py:TaskType` + `planner.py:_SYSTEM_PROMPT` |
| More task constraints | `_SYSTEM_PROMPT` rules section |
| Custom output fields | `PlannedTask` model + prompt |
| Different planning model | `config.yaml:llm.model` |