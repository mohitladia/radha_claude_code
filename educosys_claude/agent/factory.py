from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware

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
    """Create and return the LangChain agent."""

    llm = get_llm()

    # Returns:
    #   mcp_tools -> List[BaseTool]
    #   git_tool_names -> List[str]
    mcp = await get_educosys_mcp_tools()

    mcp_tools = mcp.tools
    git_tool_names = [
    tool.name
    for tool in mcp.tools_by_server.get("github", [])   # or "git", depending on your server name
    ]

    skills_prompt = build_skills_prompt()

    full_prompt = SYSTEM_PROMPT
    if skills_prompt:
        full_prompt += f"\n\n{skills_prompt}"

    tools = [
        search_codebase,
        load_skill,
        run_command,
        run_in_directory,
        read_file,
        write_file,
        append_file,
        list_directory,
        file_exists,
        *mcp_tools,
    ]

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

    # Require approval for all Git MCP tools
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

    hitl_middleware = HumanInTheLoopMiddleware(
        interrupt_on=interrupt_on,
    )

    return create_agent(
        llm,
        tools=tools,
        system_prompt=full_prompt,
        checkpointer=checkpointer,
        middleware=[hitl_middleware],
    )