"""
educosys_claude.tasks — Task execution engine for multi-step AI-driven projects.

Mirrors the `agent` package architecture:
  orchestrator → planner → executor → task_store → recovery → approval → status

Public API:
    TaskOrchestrator, handle_plan_command          # orchestrator
    create_plan, ExecutionPlan, PlannedTask        # planner
    run_subtask_agent                              # executor
    SQLiteTaskStore, TaskStatus, TaskType, Task    # task_store
    present_plan_for_approval                      # approval
    RecoveryManager                                # recovery
    show_task_status                               # status
"""

from .orchestrator import TaskOrchestrator, handle_plan_command
from .planner import create_plan, ExecutionPlan, PlannedTask
from .executor import run_subtask_agent
from .task_store import SQLiteTaskStore, TaskStatus, TaskType, Task
from .approval import present_plan_for_approval
from .recovery import RecoveryManager
from .status import show_task_status

__all__ = [
    "TaskOrchestrator", "handle_plan_command",
    "create_plan", "ExecutionPlan", "PlannedTask",
    "run_subtask_agent",
    "SQLiteTaskStore", "TaskStatus", "TaskType", "Task",
    "present_plan_for_approval",
    "RecoveryManager",
    "show_task_status",
]