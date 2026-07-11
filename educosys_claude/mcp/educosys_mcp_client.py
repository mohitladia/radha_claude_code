"""
MCP (Model Context Protocol) client — connects to external tool servers.

This module manages connections to MCP servers defined in educosys_mcp_servers.json.
Servers provide additional tools (GitHub, filesystem, docs, etc.) to the agent.

Architecture:
    1. educosys_mcp_config.py loads server configs from JSON
    2. MultiServerMCPClient (langchain-mcp-adapters) connects to all servers
    3. Returns tools grouped by server + flat list of all tools
    4. Results are cached after first load (global _cached_mcp_tools)
"""

from dataclasses import dataclass
from typing import Dict, List

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from educosys_claude.mcp.educosys_mcp_config import load_educosys_mcp_configs
from educosys_claude.observability.logger import get_logger

logger = get_logger(__name__)


@dataclass
class MCPTools:
    """Container for MCP tools returned by get_educosys_mcp_tools()."""
    tools: List[BaseTool]              # Flat list of all tools from all servers
    tools_by_server: Dict[str, List[BaseTool]]  # Tools grouped by server name


_cached_mcp_tools: MCPTools | None = None


async def get_educosys_mcp_tools() -> MCPTools:
    """
    Connect to all configured MCP servers and return their tools.

    Returns cached result on subsequent calls (avoids reconnecting).

    Returns:
        MCPTools dataclass with:
            - tools: flat list of all BaseTool instances
            - tools_by_server: dict mapping server_name -> List[BaseTool]
    """
    global _cached_mcp_tools

    # Return cached tools if already loaded
    if _cached_mcp_tools is not None:
        return _cached_mcp_tools

    # Load server configurations from educosys_mcp_servers.json
    configs = load_educosys_mcp_configs()

    if not configs:
        logger.warning("No MCP servers configured in educosys_mcp_servers.json")
        return MCPTools(tools=[], tools_by_server={})

    logger.info("Connecting to MCP servers: %s", list(configs.keys()))

    # MultiServerMCPClient handles stdio/HTTP connections to each server
    client = MultiServerMCPClient(configs)

    all_tools: List[BaseTool] = []
    tools_by_server: Dict[str, List[BaseTool]] = {}

    # Fetch tools from each server
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

    # Cache for subsequent calls
    _cached_mcp_tools = MCPTools(
        tools=all_tools,
        tools_by_server=tools_by_server,
    )

    return _cached_mcp_tools