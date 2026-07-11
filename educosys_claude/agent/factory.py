from langchain.agents import create_agent
from langchain.agents.middleware import (
    HumanInTheLoopMiddleware,
    ModelRetryMiddleware,
    ModelFallbackMiddleware,
    ToolRetryMiddleware,
    ModelCallLimitMiddleware,
    SummarizationMiddleware,
)

from educosys_claude.agent.tools import search_codebase
from educosys_claude.config import config
from educosys_claude.llm.factory import get_llm
from educosys_claude.mcp.educosys_mcp_client import get_educosys_mcp_tools
from educosys_claude.memory.short_term import get_summarization_middleware
from educosys_claude.observability.logger import get_logger
from educosys_claude.skills.skill_tools import (
    build_skills_prompt,
    load_skill,
)
from educosys_claude.tools.filesystem_tools import (
    append_file,
    file_exists,
    list_directory,
    read_file,
    write_file,
)
from educosys_claude.tools.terminal_tools import (
    run_command,
    run_in_directory,
)

logger = get_logger(__name__)


def _parse_exception_types(type_strings: list[str]) -> tuple[type[Exception], ...]:
    """Parse exception type strings into actual exception classes."""
    if not type_strings:
        return (Exception,)

    exceptions = []
    for type_str in type_strings:
        type_str = type_str.strip()
        if type_str in ("TimeoutError", "ConnectionError", "ConnectionResetError",
                        "ConnectionRefusedError", "ConnectionAbortedError",
                        "OSError", "IOError", "ValueError", "RuntimeError"):
            exceptions.append(getattr(builtins, type_str))
        else:
            # Try to import from common modules
            try:
                mod = __import__("requests.exceptions" if "HTTP" in type_str else "httpx")
                for part in ["requests.exceptions", "httpx", "openai", "anthropic"]:
                    try:
                        mod = __import__(part, fromlist=[type_str])
                        exc_class = getattr(mod, type_str)
                        exceptions.append(exc_class)
                        break
                    except (ImportError, AttributeError):
                        continue
                else:
                    logger.warning(f"Unknown exception type: {type_str}, falling back to Exception")
                    exceptions.append(Exception)
            except Exception:
                logger.warning(f"Unknown exception type: {type_str}, falling back to Exception")
                exceptions.append(Exception)

    return tuple(exceptions) if exceptions else (Exception,)


def _get_fallback_models(model_strings: list[str]):
    """Get fallback model instances from model string identifiers."""
    if not model_strings:
        return []

    from langchain.chat_models import init_chat_model
    fallbacks = []
    for model_str in model_strings:
        try:
            model = init_chat_model(model_str)
            fallbacks.append(model)
            logger.info(f"Loaded fallback model: {model_str}")
        except Exception as e:
            logger.warning(f"Failed to load fallback model {model_str}: {e}")
    return fallbacks


async def build_agent(checkpointer):
    """
    Create and return the LangChain agent with middleware stack.

    Args:
        checkpointer: LangGraph checkpointer (e.g., AsyncSqliteSaver) for persisting
                      conversation state across invocations. Required for HITL to work.
    Returns:
        Compiled LangGraph agent ready to invoke.
    """

    llm = get_llm()  # Get configured LLM (from config.py / environment)

    # Get MCP tools from external servers (GitHub, filesystem, etc.)
    mcp = await get_educosys_mcp_tools()

    mcp_tools = mcp.tools
    # Extract tool names from GitHub MCP server for approval targeting
    git_tool_names = [
        tool.name
        for tool in mcp.tools_by_server.get("github", [])   # or "git", depending on server name
    ]

    skills_prompt = build_skills_prompt()  # Load skill prompts from skills directory

    full_prompt = SYSTEM_PROMPT
    if skills_prompt:
        full_prompt += f"\n\n{skills_prompt}"

    # All tools available to the agent
    tools = [
        search_codebase,      # RAG search over codebase
        load_skill,           # Load skill definitions
        run_command,          # Execute shell commands (DANGEROUS - requires approval)
        run_in_directory,     # Execute commands in specific dir (DANGEROUS - requires approval)
        read_file,            # Read file contents
        write_file,           # Write files (DANGEROUS - requires approval)
        append_file,          # Append to files (DANGEROUS - requires approval)
        list_directory,       # List directory contents
        file_exists,          # Check if file exists
        *mcp_tools,           # MCP tools (GitHub, etc.)
    ]

    # Configure which tools require human approval before execution
    interrupt_on = {
        "run_command": {"allowed_decisions": ["approve", "edit", "reject"]},
        "run_in_directory": {"allowed_decisions": ["approve", "edit", "reject"]},
        "write_file": {"allowed_decisions": ["approve", "edit", "reject"]},
        "append_file": {"allowed_decisions": ["approve", "edit", "reject"]},
    }

    # Require approval for all Git MCP tools (create PR, push, etc.)
    interrupt_on.update(
        {
            tool_name: {"allowed_decisions": ["approve", "edit", "reject"]}
            for tool_name in git_tool_names
        }
    )

    logger.info(
        "Human-in-the-loop enabled for tools: %s",
        sorted(interrupt_on.keys()),
    )

    # ═══════════════════════════════════════════════════════════════════
    # MIDDLEWARE STACK
    # Order matters: first middleware wraps the innermost (model/tool calls)
    # On normal flow: model → model_retry → model_fallback → tool_retry → hitl → summarization
    # On HITL resume: hitl runs first to handle decisions, then summarization
    # ═══════════════════════════════════════════════════════════════════

    middleware = []

    # 1. Model Call Limit - Prevents runaway model calls
    mw_cfg = config.get("middleware", {}).get("model_call_limit", {})
    if mw_cfg.get("enabled", True):
        middleware.append(
            ModelCallLimitMiddleware(
                thread_limit=mw_cfg.get("thread_limit", 100),
                run_limit=mw_cfg.get("run_limit", 50),
                exit_behavior=mw_cfg.get("exit_behavior", "end"),
            )
        )
        logger.info(f"ModelCallLimitMiddleware enabled: thread_limit={mw_cfg.get('thread_limit')}, run_limit={mw_cfg.get('run_limit')}")

    # 2. Model Retry - Retries failed model calls with exponential backoff
    mw_cfg = config.get("middleware", {}).get("model_retry", {})
    if mw_cfg.get("enabled", True):
        retry_on = _parse_exception_types(mw_cfg.get("retry_on", []))
        middleware.append(
            ModelRetryMiddleware(
                max_retries=mw_cfg.get("max_retries", 3),
                retry_on=retry_on,
                on_failure=mw_cfg.get("on_failure", "continue"),
                backoff_factor=mw_cfg.get("backoff_factor", 2.0),
                initial_delay=mw_cfg.get("initial_delay", 1.0),
                max_delay=mw_cfg.get("max_delay", 60.0),
                jitter=mw_cfg.get("jitter", True),
            )
        )
        logger.info(f"ModelRetryMiddleware enabled: max_retries={mw_cfg.get('max_retries')}")

    # 3. Model Fallback - Falls back to alternative models if primary fails
    mw_cfg = config.get("middleware", {}).get("model_fallback", {})
    if mw_cfg.get("enabled", True):
        fallback_models = _get_fallback_models(mw_cfg.get("fallback_models", []))
        if fallback_models:
            middleware.insert(0, ModelFallbackMiddleware(fallback_models[0], *fallback_models[1:]))  # Insert at front for fallback
            logger.info(f"ModelFallbackMiddleware enabled with {len(fallback_models)} fallback model(s)")
        else:
            logger.info("ModelFallbackMiddleware enabled but no fallback models configured")

    # 4. Tool Retry - Retries failed tool calls (scoped to specific tools)
    mw_cfg = config.get("middleware", {}).get("tool_retry", {})
    if mw_cfg.get("enabled", True):
        retry_on = _parse_exception_types(mw_cfg.get("retry_on", []))
        tool_names = mw_cfg.get("tools", []) or None  # None = all tools
        middleware.append(
            ToolRetryMiddleware(
                max_retries=mw_cfg.get("max_retries", 2),
                tools=tool_names,
                retry_on=retry_on,
                on_failure=mw_cfg.get("on_failure", "continue"),
                backoff_factor=mw_cfg.get("backoff_factor", 2.0),
                initial_delay=mw_cfg.get("initial_delay", 1.0),
                max_delay=mw_cfg.get("max_delay", 30.0),
                jitter=mw_cfg.get("jitter", True),
            )
        )
        logger.info(f"ToolRetryMiddleware enabled: max_retries={mw_cfg.get('max_retries')}, tools={tool_names or 'all'}")

    # 5. Human-in-the-Loop - Pauses for approval on dangerous tools
    hitl_middleware = HumanInTheLoopMiddleware(interrupt_on=interrupt_on)
    middleware.append(hitl_middleware)

    # 6. Summarization - Compresses history when token threshold exceeded (outermost)
    summarization_middleware = get_summarization_middleware()
    middleware.append(summarization_middleware)

    logger.info("Middleware stack (inner→outer): %s", [m.__class__.__name__ for m in middleware])

    # Create the agent with middleware stack
    return create_agent(
        llm,
        tools=tools,
        system_prompt=full_prompt,
        checkpointer=checkpointer,
        middleware=middleware,
    )


SYSTEM_PROMPT = """
You are a senior software engineer with deep knowledge of the codebase.
Always use the search_codebase tool before answering any question.
Reference specific file names, function names and line numbers in your answers.
If you cannot find the answer in the codebase, say so explicitly.
"""

# Import builtins at module level for _parse_exception_types
import builtins