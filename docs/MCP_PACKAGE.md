# 🔌 MCP Package

The `mcp` package (Model Context Protocol) enables integration with external tools and services through standardized MCP servers. It allows the agent to access capabilities beyond its built-in tools, such as GitHub integration, by connecting to MCP-compatible services.

## 📁 Package Structure

```
educosys_claude/mcp/
├── __init__.py
├── educosys_mcp_client.py   # MCP client for connecting to servers
└── educosys_mcp_config.py   # MCP configuration loader
```

## 🧩 Components

### 1. MCP Client (`educosys_mcp_client.py`)

**Purpose**: Connects to configured MCP servers and provides their tools to the agent. Implements caching to avoid reconnecting to servers on every request.

**Key Functions**:
- `get_educosys_mcp_tools() -> list[Tool]`: Main function that returns cached MCP tools from all configured servers

**How It Works**:
1. Uses a global cache (`_educosys_mcp_tools`) to store tools after first connection
2. On first call, loads MCP server configurations via `load_educosys_mcp_configs()`
3. Connects to all configured MCP servers using `MultiServerMCPClient`
4. Retrieves tools from each server and combines them into a single list
5. Returns the cached list on subsequent calls

**Key Features**:
- **Caching**: Prevents reconnecting to MCP servers on every tool request
- **Error Handling**: Gracefully handles missing or misconfigured servers
- **Logging**: Provides detailed logs of connection attempts and tool loading
- **Standard Integration**: Uses `langchain_mcp_adapters` for MCP compliance

### 2. MCP Configuration Loader (`educosys_mcp_config.py`)

**Purpose**: Loads and processes MCP server configuration from `educosys_mcp_servers.json`, resolving environment variables in the process.

**Key Functions**:
- `load_educosys_mcp_configs() -> dict`: Loads MCP server configurations with environment variable resolution

**How It Works**:
1. Reads JSON configuration from `educosys_mcp_servers.json` (relative to package)
2. Parses the `mcp_servers` object from the JSON
3. Resolves environment variables using pattern `${VAR_NAME}` replacement
4. Returns processed configuration dictionary ready for `MultiServerMCPClient`

**Environment Variable Resolution**:
- Uses regex pattern `r"\$\{(\w+)\}"` to find `${VAR}` patterns
- Replaces each pattern with `os.getenv(var_name, "")` (empty string if not found)
- Recursively processes nested objects and arrays

## 🔧 How It All Works Together

### MCP Integration Flow
```
Application Start
     ↓
main.py -> agent/factory.py:build_agent()
     ↓
agent/factory.py calls get_educosys_mcp_tools()
     ↓
mcp/educosys_mcp_client.py:get_educosys_mcp_tools()
     ↓
  Check global cache _educosys_mcp_tools
     ↓
  If empty:
      ↓
      mcp/educosys_mcp_config.py:load_educosys_mcp_configs()
         ↓
         Read educosys_mcp_servers.json
         ↓
         Parse and resolve environment variables
         ↓
         Return mcp_servers dict
      ↓
      Create MultiServerMCPClient with configs
      ↓
      Call client.get_tools() to retrieve tools from all servers
      ↓
      Cache result in _educosys_mcp_tools
      ↓
      Log number of tools loaded
     ↓
  Return cached tool list
     ↓
agent/factory.py:build_agent()
     ↓
Add MCP tools to agent's tool list
     ↓
Create and return LangChain agent with MCP tools available
     ↓
Agent can now use MCP tools during reasoning process
```

### Configuration Loading Process
```
load_educosys_mcp_configs()
     ↓
1. Determine config file path:
   Path(__file__).parent.parent / "educosys_mcp_servers.json"
     ↓
2. Read and parse JSON file
     ↓
3. Extract "mcp_servers" object
     ↓
4. For each value in the object:
     ↓
   a. If string: resolve ${VAR_NAME} patterns
   b. If dict: recursively process all values
   c. If list: recursively process all items
   d. Else: return value unchanged
     ↓
5. Return processed configuration dict
```

## 📝 Configuration File (`educosys_mcp_servers.json`)

The MCP server configuration is stored in `educosys_mcp_servers.json` at the project root:

```json
{
  "mcp_servers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"
      },
      "transport": "stdio"
    }
  }
}
```

### Configuration Structure
- **Top-level**: Object with `mcp_servers` key
- **mcp_servers**: Object where each key is a server name and value is server configuration
- **Server Configuration**:
  - `command`: The executable to run (e.g., "npx", "python")
  - `args`: List of arguments to pass to the command
  - `env`: Object mapping environment variable names to values (can include `${VAR_NAME}` for resolution)
  - `transport`: Communication mechanism (usually "stdio" for local processes)

### Environment Variable Resolution
Values in the `env` object can contain placeholders that are replaced at runtime:
- `${GITHUB_TOKEN}` → replaced with value of `GITHUB_TOKEN` environment variable
- If variable is not set, replaced with empty string
- Multiple variables can be in one string: `"prefix${VAR1}middle${VAR2}suffix"`

## 📝 Usage Examples

### Direct MCP Tool Usage
```python
from educosys_claude.mcp.educosys_mcp_client import get_educosys_mcp_tools

# Get all available MCP tools
mcp_tools = await get_educosys_mcp_tools()
print(f"Available MCP tools: {[tool.name for tool in mcp_tools]}")

# Use a specific tool (example for GitHub)
github_tool = next((tool for tool in mcp_tools if tool.name == "github_search_repositories"), None)
if github_tool:
    result = await github_tool.ainvoke({"query": "language:python"})
    print(result)
```

### Integration in Main Application
```python
# In educosys_claude/main.py (via agent factory)
from educosys_claude.mcp.educosys_mcp_client import get_educosys_mcp_tools

async def build_agent(checkpointer):
    llm = get_llm()
    # Get MCP tools (cached after checking cache, connecting if needed)
    mcp_tools = await get_educosys_mcp_tools()
    tools = [
        search_codebase,
        run_command,
        run_in_directory,
        read_file,
        write_file,
        append_file,
        delete_file,
        list_directory,
        file_exists,
        *mcp_tools,  # <-- MCP tools added here
    ]
    # ... rest of agent creation
```

### Custom MCP Server Configuration
To add a new MCP server, edit `educosys_mcp_servers.json`:
```json
{
  "mcp_servers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"
      },
      "transport": "stdio"
    },
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem"],
      "env": {},
      "transport": "stdio"
    }
  }
}
```

## ⚙️ Configuration

MCP configuration is controlled by:
1. **File**: `educosys_mcp_servers.json` in project root
2. **Environment Variables**: Referenced in the JSON configuration using `${VAR_NAME}` syntax

### Example Environment Setup
```bash
# Set required environment variables
export GITHUB_TOKEN="ghp_your_actual_token_here"
# Optional: set others as needed by your MCP servers
```

### Configuration Validation
The system handles missing configurations gracefully:
- If `educosys_mcp_servers.json` is missing or invalid: logs warning and returns empty tool list
- If `mcp_servers` key is missing: logs warning and returns empty tool list
- If individual server configs are invalid: skips that server and continues with others
- If environment variables are unresolved: replaces with empty string (may cause server startup failures)

## 🔄 Integration Points

The MCP package is used by:
1. **Agent Package** (`agent/factory.py`):
   - Calls `get_educosys_mcp_tools()` to retrieve available MCP tools
   - Adds MCP tools to the agent's tool list alongside built-in tools
   - Enables the LLM agent to reason about and use MCP-provided capabilities

2. **Main Application** (`main.py`):
   - Indirectly through agent initialization
   - MCP servers are started when the agent is first built (lazy initialization via caching)

## 📊 Performance Characteristics

### Connection Overhead
- **First call**: Connects to all configured MCP servers (can take seconds depending on server startup time)
- **Subsequent calls**: Returns cached tool list near-instantly (microseconds)
- **Connection persistence**: Maintains connections to MCP servers for the duration of the agent lifetime

### Tool Execution
- **Performance**: Depends entirely on the specific MCP server and tool being invoked
- **Communication**: Uses stdio transport by default (fast local inter-process communication)
- **Timeouts**: Inherits timeout behavior from the underlying MCP client implementation

### Resource Usage
- **Memory**: Scales with number of tools from all connected servers
- **Processes**: One subprocess per MCP server (for stdio transport)
- **File descriptors**: Limited by subprocesses and their internal operations

## 🛠️ Customization & Extension

### Adding New MCP Servers
To add a new MCP server:
1. Install the MCP server package (if needed): `npm install -y @modelcontextprotocol/server-{name}` or similar
2. Add configuration to `educosys_mcp_servers.json`:
   ```json
   "server_name": {
     "command": "executable_to_run",
     "args": ["arg1", "arg2"],
     "env": {
       "ENV_VAR_NAME": "${ACTUAL_ENV_VAR}"
     },
     "transport": "stdio"
   }
   ```
3. Set required environment variables in your environment
4. Restart the application to pick up new configuration

### Creating Custom MCP Servers
To create your own MCP server:
1. Follow MCP specification: https://modelcontextprotocol.io/
2. Implement server using one of the SDKs (Python, TypeScript, etc.)
3. Ensure it communicates via stdio (or other supported transport)
4. Add configuration to `educosys_mcp_servers.json`
5. Test with `get_educosys_mcp_tools()` to verify tools are loaded

### Modifying Transport Method
While the current implementation uses stdio transport, you could:
1. Modify `educosys_mcp_client.py` to support other transports (HTTP, WebSocket, etc.)
2. Update configuration schema in `educosys_mcp_servers.json`
3. Adjust `MultiServerMCPClient` initialization accordingly

### Error Handling Enhancements
To improve robustness:
1. Add retry logic for failed server connections
2. Implement health checks for MCP servers
3. Add configurable timeouts for server startup and tool execution
4. Implement partial failure handling (continue if some servers fail)

## 💡 Best Practices

### Security Considerations
1. **Environment Variables**: Never commit actual secrets to `educosys_mcp_servers.json` - always use `${VAR}` placeholders
2. **Least Privilege**: Configure MCP servers with minimal necessary permissions
3. **Network Exposure**: Be aware of what network resources MCP servers can access
4. **Input Validation**: Remember that MCP tools receive agent-generated input - validate appropriately in your MCP servers

### Configuration Management
1. **Version Control**: Keep `educosys_mcp_servers.json` in version control with placeholder values
2. **Environment Specific**: Consider having different configs for dev/stage/prod via environment-specific files
3. **Documentation**: Comment your MCP server configurations to explain their purpose and required environment variables

### Performance Optimization
1. **Lazy Loading**: Current implementation already caches tools after first connection
2. **Selective Loading**: For applications that don't need all MCP servers, consider:
   - Adding enabled/disabled flags to server config
   - Modifying `get_educosys_mcp_tools()` to filter based on configuration
3. **Connection Pooling**: For HTTP-based MCP servers, consider connection reuse strategies

### Troubleshooting MCP Issues
1. **No tools appearing**:
   - Check if `educosys_mcp_servers.json` exists and is valid JSON
   - Verify `mcp_servers` key is present in the JSON
   - Check server logs for startup errors
   - Ensure environment variables are set correctly

2. **Server fails to start**:
   - Verify the command and args are correct
   - Check if required dependencies are installed
   - Look at subprocess stderr (available in logs if enabled)
   - Test the command manually in terminal

3. **Tools not working as expected**:
   - Test the MCP server directly if possible
   - Check tool schemas and expected input/output formats
   - Verify agent is correctly invoking tools with proper parameters

4. **Performance issues**:
   - Monitor MCP server resource usage
   - Consider if some servers can be started on-demand rather than at startup
   - Evaluate whether all connected servers are actually needed

## 🌐 Example MCP Servers

### Official MCP Servers
- **GitHub**: `@modelcontextprotocol/server-github` - GitHub API access
- **Filesystem**: `@modelcontextprotocol/server-filesystem` - Local file system operations
- **Memory**: `@modelcontextprotocol/server-memory` - Persistent key-value store
- **PostgreSQL**: `@modelcontextprotocol/server-postgres` - PostgreSQL database access
- **Fetch**: `@modelcontextprotocol/server-fetch` - HTTP fetching capabilities

### Community Servers
- Many community-maintained servers exist for various services (Slack, Docker, Kubernetes, etc.)
- Check MCP registry for available options

## 🔄 Integration Workflow Examples

### GitHub Integration Workflow
```
User: "Find recent issues about authentication in our repo"
     ↓
Agent reasons: I need to search GitHub issues
     ↓
Agent selects github_search_issues tool from MCP tools
     ↓
Agent invokes tool with parameters: {repository: "owner/repo", query: "authentication", state: "open"}
     ↓
MCP GitHub server:
   ↓
   1. Receives request via stdio
   ↓
   2. Uses GITHUB_TOKEN env var to authenticate
   ↓
   3. Calls GitHub API search issues endpoint
   ↓
   4. Returns formatted results
     ↓
Agent receives results and forms final answer for user
```

### Filesystem Integration Workflow
```
User: "What's in the src/config directory?"
     ↓
Agent reasons: I should list the directory contents
     ↓
Agent selects filesystem_list_directory tool from MCP tools
     ↓
Agent invokes tool with parameter: {path: "/project/src/config"}
     ↓
MCP Filesystem server:
   ↓
   1. Receives request via stdio
   ↓
   2. Checks if path exists and is directory
   ↓
   3. Returns list of files and subdirectories
     ↓
Agent formats and returns the directory listing to user
```