import json
import os
import pprint
from langgraph.types import Command
from rich.console import Console
from rich.prompt import Prompt

from educosys_claude.observability.logger import get_logger
from educosys_claude.memory import get_long_term_memory

try:
    from educosys_claude.agent.hitl_github_actions import handle_query_github_hitl
    HITL_GITHUB_AVAILABLE = True
except ImportError:
    HITL_GITHUB_AVAILABLE = False

logger = get_logger(__name__)
console = Console()


def _in_github_actions() -> bool:
    """Detect if running inside GitHub Actions."""
    return os.getenv("GITHUB_ACTIONS") == "true"


async def handle_query(agent, question: str, thread_id: str) -> str:
    """
    Entry point for all user queries.
    Auto-detects GitHub Actions and uses appropriate HITL handler.
    """
    logger.info(f"Handling query for session {thread_id}: {question}")
    agent_config = {"configurable": {"thread_id": thread_id}}

    try:
        # Retrieve relevant long-term memories and prepend to question
        ltm = get_long_term_memory()
        memory_context = await ltm.get_context_for_query(question)
        if memory_context:
            question = f"{memory_context}\n\nUser question: {question}"

        # Use GitHub Actions HITL if in CI, otherwise local prompt
        if _in_github_actions() and HITL_GITHUB_AVAILABLE:
            logger.info("GitHub Actions detected - using GitHub HITL handler")
            return await handle_query_github_hitl(agent, question, thread_id)

        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": question}]},
            config=agent_config,
            version="v2",
        )

        while result.interrupts:
            result = await _resolve_interrupt(agent, result, agent_config)

        return result.value["messages"][-1].content

    except Exception as e:
        logger.error(f"Agent error: {e}")
        return f"Error: {e}"
    finally:
        # Fire-and-forget: extract facts from this conversation turn
        # Runs in background so it doesn't block the response
        try:
            ltm = get_long_term_memory()
            # Get the final messages from result for fact extraction
            if 'result' in locals() and hasattr(result, 'value') and result.value:
                messages = result.value.get("messages", [])
                if messages:
                    # Schedule background extraction
                    import asyncio
                    asyncio.create_task(ltm.extract_and_store_facts(messages, thread_id))
        except Exception as e:
            logger.debug(f"Background fact extraction skipped: {e}")


async def _resolve_interrupt(agent, result, agent_config: dict):
    """Prompt the user for approve/edit/reject on each pending tool call,
    then resume the agent with those decisions."""
    interrupt_payload = result.interrupts[0].value
    decisions = []

    for action_request in interrupt_payload["action_requests"]:
        tool_name = action_request["name"]
        tool_args = action_request["args"]

        console.print(
            f"\n[bold yellow]Approval needed:[/bold yellow] "
            f"{tool_name}({tool_args})"
        )
        choice = Prompt.ask(
            "[bold]Approve / Edit / Reject?[/bold]",
            choices=["a", "e", "r"],
            default="a",
        )

        if choice == "a":
            decisions.append({"type": "approve"})
        elif choice == "e":
            new_args_raw = Prompt.ask(
                f"New args (JSON) [{tool_args}]", default=""
            ).strip()
            try:
                new_args = json.loads(new_args_raw) if new_args_raw else tool_args
            except json.JSONDecodeError:
                console.print("[red]Invalid JSON, using original args.[/red]")
                new_args = tool_args
            decisions.append({
                "type": "edit",
                "edited_action": {"name": tool_name, "args": new_args},
            })
        else:
            reason = Prompt.ask("Reason for rejection", default="")
            decisions.append({"type": "reject", "message": reason})

    logger.info(
    "Resume decisions:\n%s",
    pprint.pformat(decisions),
)
    logger.info(f"Resuming with decisions: {decisions}")

    result = await agent.ainvoke(
    Command(resume={"decisions": decisions}),
    config=agent_config,
    version="v2",
)
    return result