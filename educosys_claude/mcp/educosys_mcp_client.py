from langchain_mcp_adapters.client import MultiServerMCPClient
from educosys_claude.mcp.educosys_mcp_config import load_educosys_mcp_configs
from educosys_claude.observability.logger import get_logger


logger = get_logger(__name__)


_educosys_mcp_tools = None


async def get_educosys_mcp_tools() -> list:
   """Connect to all configured MCP servers and return their tools (cached)."""
   global _educosys_mcp_tools
   if _educosys_mcp_tools is not None:
       return _educosys_mcp_tools


   configs = load_educosys_mcp_configs()
   if not configs:
       logger.warning("No MCP servers configured in educosys_mcp_servers.json")
       return []


   logger.info(f"Connecting to MCP servers: {list(configs.keys())}")
   client = MultiServerMCPClient(configs)
   _educosys_mcp_tools = await client.get_tools()
   logger.info(f"Loaded {len(_educosys_mcp_tools)} tools from MCP servers")
   return _educosys_mcp_tools
