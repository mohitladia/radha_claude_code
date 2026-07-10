from dataclasses import dataclass
from typing import Dict, List

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from educosys_claude.mcp.educosys_mcp_config import load_educosys_mcp_configs
from educosys_claude.observability.logger import get_logger

logger = get_logger(__name__)


@dataclass
class MCPTools:
    tools: List[BaseTool]
    tools_by_server: Dict[str, List[BaseTool]]


_cached_mcp_tools: MCPTools | None = None


async def get_educosys_mcp_tools() -> MCPTools:
    """
    Connect to all configured MCP servers and return:
      - all tools
      - tools grouped by server

    Results are cached after the first load.
    """

    global _cached_mcp_tools

    if _cached_mcp_tools is not None:
        return _cached_mcp_tools

    configs = load_educosys_mcp_configs()

    if not configs:
        logger.warning("No MCP servers configured in educosys_mcp_servers.json")
        return MCPTools(
            tools=[],
            tools_by_server={},
        )

    logger.info("Connecting to MCP servers: %s", list(configs.keys()))

    client = MultiServerMCPClient(configs)

    all_tools: List[BaseTool] = []
    tools_by_server: Dict[str, List[BaseTool]] = {}

    for server_name in configs:
        server_tools = await client.get_tools(server_name=server_name)

        logger.info(
            "Loaded %d tools from '%s': %s",
            len(server_tools),
            server_name,
            [tool.name for tool in server_tools],
        )

        tools_by_server[server_name] = server_tools
        all_tools.extend(server_tools)

    logger.info(
        "Loaded %d MCP tools from %d servers",
        len(all_tools),
        len(tools_by_server),
    )

    _cached_mcp_tools = MCPTools(
        tools=all_tools,
        tools_by_server=tools_by_server,
    )

    return _cached_mcp_tools