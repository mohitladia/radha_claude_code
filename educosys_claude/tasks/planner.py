from __future__ import annotations


from pydantic import BaseModel
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model


from educosys_claude.config import config
from educosys_claude.tasks.task_store import TaskType
from educosys_claude.observability.logger import get_logger


logger = get_logger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Pydantic models — planner output schema (validated by LLM structured output)
# ──────────────────────────────────────────────────────────────────────

class PlannedTask(BaseModel):
    """
    Single task in an execution plan.

    All fields are required for the planner LLM to produce a complete,
    executable plan. The orchestrator and executor rely on every field.
    """
    id: str                          # stable snake_case: task_001, task_002, ...
    title: str
    description: str
    task_type: TaskType
    depends_on: list[str]            # task IDs that must complete first (DAG edges)
    estimated_minutes: int           # rough effort estimate for planning/scheduling
    output_files: list[str]          # files this task will CREATE (not just modify)
    acceptance_criteria: list[str]   # 3-5 concrete, verifiable "done" checks


class ExecutionPlan(BaseModel):
    """
    Complete execution plan for a software goal.

    Produced by the LLM planner, reviewed by human, then persisted to SQLite.
    """
    project_name: str
    goal_summary: str
    tech_stack: list[str]
    total_estimated_hours: float
    tasks: list[PlannedTask]
    risks: list[str]
    assumptions: list[str]


# ──────────────────────────────────────────────────────────────────────
# Planner system prompt — instructs LLM to produce a valid ExecutionPlan
# ──────────────────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a senior software architect. Given a software goal, produce a detailed
ExecutionPlan broken into concrete tasks for an AI agent to implement.


Rules:
- 5 to 20 tasks
- Task IDs must be stable snake_case: task_001, task_002, ...
- depends_on must reference valid task IDs in the same plan
- Ordering must form a valid DAG (no cycles): architecture → schema → config → core → tests → integration
- output_files must list every file the task will write to disk
- acceptance_criteria must be concrete and verifiable (3-5 items per task)
- task_type must be one of: design, implement, test, review, integrate, configure
"""


def create_plan(goal: str, extra_context: str = "") -> ExecutionPlan:
    """
    Call the LLM planner and return a validated ExecutionPlan.

    Uses structured output (Pydantic model) so the LLM must return valid JSON
    matching the schema. Temperature=0 for deterministic planning.

    Args:
        goal: High-level software goal from user (e.g., "build a REST API for todos")
        extra_context: Optional feedback from human approval loop for re-planning

    Returns:
        ExecutionPlan with 5-20 tasks, validated by Pydantic
    """
    provider = config["llm"]["provider"]
    model    = config["llm"]["model"]

    # Initialize LLM with provider:model syntax (e.g., "anthropic:claude-3-5-sonnet")
    llm = init_chat_model(f"{provider}:{model}", temperature=0)

    # Create a structured-output agent — forces LLM to return ExecutionPlan JSON
    planner_agent = create_agent(
        llm,
        tools=[],                          # planner has no tools; pure reasoning
        system_prompt=_SYSTEM_PROMPT,
        response_format=ExecutionPlan,     # Pydantic model for structured output
    )

    user_message = f"Goal: {goal}"
    if extra_context:
        user_message += f"\n\nAdditional context / change requests:\n{extra_context}"

    # Invoke planner agent — returns dict with "structured_response" key
    result = planner_agent.invoke({"messages": [{"role": "user", "content": user_message}]})
    plan: ExecutionPlan = result["structured_response"]

    logger.info(f"Plan created: {plan.project_name} with {len(plan.tasks)} tasks")
    return plan