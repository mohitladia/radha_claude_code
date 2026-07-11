from langchain.agents import create_agent  # Factory function to create a LangGraph agent
from langchain.agents.middleware import (
    HumanInTheLoopMiddleware,    # Pauses agent before dangerous tools for human approval
)

from educosys_claude.agent.tools import search_codebase
from educosys_claude.llm.factory import get_llm
from educosys_claude.mcp.educosys_mcp_client import get_educosys_mcp_tools
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


SYSTEM_PROMPT = """
You are a senior software engineer with deep knowledge of the codebase.
Always use the search_codebase tool before answering any question.
Reference specific file names, function names and line numbers in your answers.
If you cannot find the answer in the codebase, say so explicitly.
"""


async def build_agent(checkpointer):
    """
    Create and return the LangChain agent with HITL middleware.

    Args:
        checkpointer: LangGraph checkpointer (e.g., AsyncSqliteSaver) for persisting
                      conversation state across invocations. Required for HITL to work.
    Returns:
        Compiled LangGraph agent ready to invoke.
    """

    llm = get_llm()  # Get configured LLM (from config.py / environment)

    # Get MCP tools from external servers (GitHub, filesystem, etc.)
    # Returns object with .tools (list of BaseTool) and .tools_by_server (dict)
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
    # Keys = tool names, Values = allowed decision types
    interrupt_on = {
        "run_command": {
            "allowed_decisions": ["approve", "edit", "reject"],
        },
        "run_in_directory": {
            "allowed_decisions": ["approve", "edit", "reject"],
        },
        "write_file": {
            "allowed_decisions": ["approve", "edit", "reject"],
        },
        "append_file": {
            "allowed_decisions": ["approve", "edit", "reject"],
        },
    }

    # Require approval for all Git MCP tools (create PR, push, etc.)
    interrupt_on.update(
        {
            tool_name: {
                "allowed_decisions": ["approve", "edit", "reject"],
            }
            for tool_name in git_tool_names
        }
    )

    logger.info(
        "Human-in-the-loop enabled for tools: %s",
        sorted(interrupt_on.keys()),
    )

    # Middleware 1: HumanInTheLoopMiddleware
    # Intercepts tool calls matching `interrupt_on` keys, pauses graph execution,
    # and waits for human decision (approve/edit/reject) via Command(resume=...)
    hitl_middleware = HumanInTheLoopMiddleware(
        interrupt_on=interrupt_on,
    )

    # NOTE: ClearToolUsesEdit (via ContextEditingMiddleware) is designed for
    # token budget management, not HITL history repair. It clears old tool outputs
    # when token count exceeds trigger threshold.
    #
    # For HITL orphaned tool_calls repair, we rely on LangGraph's built-in
    # version="v2" + Command(resume=...) mechanism which handles history correctly.
    # If you still get "tool_calls without matching tool messages" errors,
    # consider adding ContextEditingMiddleware with ClearToolUsesEdit(clear_tool_inputs=True)
    # but note it only triggers on token count, not on interrupt resume.
    #
    # create_agent(
    #     ...,
    #     middleware=[ContextEditingMiddleware(edits=[ClearToolUsesEdit(clear_tool_inputs=True)]), hitl_middleware],
    # )

    # Create the agent with middleware stack.
    return create_agent(
        llm,
        tools=tools,
        system_prompt=full_prompt,
        checkpointer=checkpointer,  # Persists state (messages, interrupts) to SQLite
        middleware=[hitl_middleware],
    )