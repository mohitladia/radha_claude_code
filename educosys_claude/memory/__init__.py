"""
Memory package - Short-term and long-term memory for conversation persistence.
"""

from educosys_claude.memory.short_term import (
    get_checkpointer_db_path,
    get_checkpointer,
    get_summarization_middleware,
)

from educosys_claude.memory.long_term import (
    LongTermMemory,
    MemoryFact,
    get_long_term_memory,
)

from educosys_claude.memory.session import (
    get_current_session,
    new_session,
    switch_session,
)

__all__ = [
    # Short-term
    "get_checkpointer_db_path",
    "get_checkpointer",
    "get_summarization_middleware",
    # Long-term
    "LongTermMemory",
    "MemoryFact",
    "get_long_term_memory",
    # Session management
    "get_current_session",
    "new_session",
    "switch_session",
]