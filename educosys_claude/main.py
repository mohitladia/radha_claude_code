"""
Main entry point for Educosys Claude — RAG-powered coding assistant.

Architecture:
    1. Initialize LLM, embedder, indexer, MCP tools
    2. Build LangGraph agent with HITL middleware (factory.build_agent)
    3. Create/restore SQLite checkpointer for conversation persistence
    4. Run REPL loop accepting /ask, /new_session, /switch, /show_index commands
"""

import asyncio
from pathlib import Path
from dotenv import load_dotenv
from rich.console import Console
from rich.prompt import Prompt

from educosys_claude.config import config
from educosys_claude.context.indexers.factory import get_indexer, get_index_inspector
from educosys_claude.llm.factory import get_llm, get_embedder
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from educosys_claude.agent.factory import build_agent
from educosys_claude.memory.short_term import get_checkpointer_db_path
from educosys_claude.agent.orchestrator import handle_query
from educosys_claude.memory.session import get_current_session, new_session, switch_session
from educosys_claude.observability.logger import get_logger
from educosys_claude.tasks.orchestrator import handle_plan_command
from educosys_claude.tasks.status import show_task_status



# Load .env from project root (parent of educosys_claude package)
load_dotenv(Path(__file__).parent.parent / ".env")

console = Console()
logger = get_logger(__name__)


def get_or_create_index():
    """
    Build or load the codebase index for the current working directory.

    The indexer uses the configured RAG mode (config.yaml) to chunk and embed
    the codebase into the vector store (Qdrant/ChromaDB).
    """
    repo_path = str(Path.cwd())
    logger.info(f"Checking index for: {repo_path}")
    console.print(f"[dim]Checking index for {repo_path}...[/dim]")
    return get_indexer()(repo_path)


async def initialize(checkpointer):
    """
    Bootstrap all components before starting the REPL.

    Args:
        checkpointer: AsyncSqliteSaver for LangGraph state persistence

    Returns:
        tuple: (llm, embedder, index, agent, session_id)
    """
    llm = get_llm()
    embedder = get_embedder()
    console.print(f"[dim]LLM: {config['llm']['provider']} / {config['llm']['model']}[/dim]")
    console.print(f"[dim]Embedder: {config['embeddings']['provider']} / {config['embeddings']['model']}[/dim]")

    index = get_or_create_index()
    agent = await build_agent(checkpointer)

    session_id = get_current_session()
    console.print(f"[dim]Session: {session_id}[/dim]")
    console.print(f"[green]✓ Ready[/green]\n")
    return llm, embedder, index, agent, session_id


async def _run_async():
    """Main async REPL loop."""
    logger.info("Starting Educosys Claude")
    console.print("\n[bold blue]Educosys Claude[/bold blue] — RAG-powered code assistant")

    # Async context manager for SQLite checkpointer (persists conversation state)
    async with AsyncSqliteSaver.from_conn_string(get_checkpointer_db_path()) as checkpointer:
        llm, embedder, index, agent, session_id = await initialize(checkpointer)
        console.print("Type [bold]'/exit'[/bold] to quit\n")

        while True:
            user_input = Prompt.ask("[bold green]>[/bold green]")

            if not user_input.strip():
                continue

            if user_input.lower() in ("/exit", "/quit"):
                logger.info("Shutting down")
                console.print("[dim]Goodbye![/dim]")
                break

            elif user_input.startswith("/ask "):
                question = user_input.removeprefix("/ask ").strip()
                logger.info(f"Ask command received: {question}")
                console.print(f"[dim]Searching for: {question}...[/dim]")
                response = await handle_query(agent, question, session_id)
                console.print(response)

            elif user_input.startswith("/plan "):
               goal = user_input.removeprefix("/plan ").strip()
               logger.info(f"Plan command received: {goal}")
               await handle_plan_command(goal)
            elif user_input == "/task_status":
               show_task_status()
            elif user_input == "/new_session":
                session_id = new_session()
                console.print(f"[green]New session started: {session_id}[/green]")
            elif user_input.startswith("/switch "):
                target = user_input.removeprefix("/switch ").strip()
                session_id = switch_session(target)
                console.print(f"[green]Switched to session: {session_id}[/green]")

            elif user_input == "/session":
                console.print(f"[dim]Current session: {session_id}[/dim]")

            elif user_input == "/show_index":
                logger.info("Showing index")
                get_index_inspector()(index)

            else:
                logger.warning(f"Unknown command received: {user_input}")
                console.print("[yellow]Unknown command. Try:[/yellow]")
                console.print("  [bold]/ask <question>[/bold]          — ask a question about the codebase")
                console.print("  [bold]/show_index[/bold]              — show all chunks in the index")
                console.print("  [bold]/new_session[/bold]             — start a fresh conversation")
                console.print("  [bold]/switch <session_id>[/bold]     — resume a past session")
                console.print("  [bold]/session[/bold]                 — show current session id")
                console.print("  [bold]/plan <goal>[/bold] — generate and execute a plan")
                console.print("  [bold]/task_status[/bold] — show task progress for active project")



def run():
    """Synchronous entry point — runs the async REPL."""
    asyncio.run(_run_async())


if __name__ == "__main__":
    run()