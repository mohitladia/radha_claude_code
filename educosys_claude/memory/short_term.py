"""
Short-term memory (conversation persistence) using LangGraph SQLite checkpointer.

Also provides SummarizationMiddleware for automatic conversation compression.
"""

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langchain.agents.middleware import SummarizationMiddleware
from pathlib import Path


from educosys_claude.config import config
from educosys_claude.llm.factory import get_llm
from educosys_claude.observability.logger import get_logger

logger = get_logger(__name__)


def get_checkpointer_db_path() -> str:
    """
    Return the SQLite database path for the checkpointer.

    Config: memory.db_path (e.g., ".radha/memory/memory.db")
    Creates parent directories if needed.
    """
    db_path = config["memory"]["db_path"]
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Using SQLite checkpointer at {db_path}")
    return db_path


def get_checkpointer() -> AsyncSqliteSaver:
    """
    Create and return an AsyncSqliteSaver checkpointer.

    This persists LangGraph state (messages, interrupts, tools) to SQLite
    so conversations survive restarts and HITL pauses work across invocations.

    Usage in main.py:
        async with AsyncSqliteSaver.from_conn_string(get_checkpointer_db_path()) as checkpointer:
            agent = await build_agent(checkpointer)
            # agent now has persistent memory
    """
    db_path = get_checkpointer_db_path()
    return AsyncSqliteSaver.from_conn_string(db_path)


def get_summarization_middleware() -> SummarizationMiddleware:
    """
    Return a SummarizationMiddleware instance for conversation compression.

    This middleware automatically summarizes old messages when token count
    exceeds the configured threshold, keeping the conversation within
    the LLM's context window.

    Config keys (config.yaml):
        memory.summarize_at_tokens: int — trigger summarization at this token count
        memory.keep_last_messages: int — always preserve last N messages uncompressed

    Returns:
        Configured SummarizationMiddleware instance.
    """
    return SummarizationMiddleware(
        model=get_llm(),
        trigger=("tokens", config["memory"]["summarize_at_tokens"]),
        keep=("messages", config["memory"]["keep_last_messages"]),
    )