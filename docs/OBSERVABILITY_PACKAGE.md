# 👁️ Observability Package

The `observability` package provides logging and monitoring capabilities for the application. It configures structured logging with appropriate log levels to help debug issues while suppressing noisy third-party library logs.

## 📁 Package Structure

```
educosys_claude/observability/
├── __init__.py
└── logger.py           # Logging configuration and utility
```

## 🧩 Components

### Logger (`logger.py`)

**Purpose**: Configures application logging with appropriate log levels - sets root logger to WARNING to suppress noisy third-party logs while allowing application loggers to run at DEBUG level for detailed tracing.

**Key Functions**:
- `get_logger(name: str) -> logging.Logger`: Returns a configured logger instance for the given name

**How It Works**:
1. Configures the root logger with:
   - Level: WARNING (to suppress noise from libraries like OpenAI, httpcore, etc.)
   - Format: `"%(asctime)s | %(levelname)s | %(name)s | %(message)s"`
2. Returns application-specific loggers set to DEBUG level for detailed tracing
3. Each module gets its own logger via `__name__` for precise tracing

**Log Levels**:
- **ROOT LOGGER**: WARNING - Only shows warnings and errors from third-party libraries
- **APPLICATION LOGGERS**: DEBUG - Shows all logs from application code for detailed tracing

**Configuration**:
The logging is configured once at module import time using `logging.basicConfig()`. This means:
- Only the first call to basicConfig has effect
- All application loggers inherit the format but can override the level
- Application code should use `get_logger(__name__)` to get properly configured loggers

## 🔧 How It Works Together

### Logging Initialization
```
Module Import
     ↓
observability/logger.py: logging.basicConfig() called
     ↓
  Root logger set to WARNING with specific format
     ↓
Module-specific code calls get_logger(__name__)
     ↓
  Returns logger with name set to module's __name__
     ↓
  Logger level set to DEBUG (overriding root WARNING for this logger)
     ↓
Logs emitted at DEBUG level and above are captured
```

### Usage in Application Code
```python
# At the top of each module
from educosys_claude.observability.logger import get_logger

# Create logger for this module
logger = get_logger(__name__)

# Then use throughout the module
logger.debug("Detailed debugging information")
logger.info("General operational information")
logger.warning("Warning about potential issues")
logger.error("Error that occurred")
logger.critical("Critical error requiring immediate attention")
```

## 📝 Usage Examples

### Basic Usage
```python
from educosys_claude.observability.logger import get_logger

logger = get_logger(__name__)

def example_function():
    logger.debug("Entering example_function")
    try:
        # Do some work
        result = some_operation()
        logger.info(f"Operation completed successfully: {result}")
        return result
    except Exception as e:
        logger.error(f"Operation failed: {e}", exc_info=True)
        raise
    finally:
        logger.debug("Exiting example_function")
```

### Usage in Different Layers
**In main.py**:
```python
logger = get_logger(__name__)
logger.info("Starting Educosys Claude")
# ... 
logger.info("Shutting down")
```

**In agent/factory.py**:
```python
logger = get_logger(__name__)
logger.info(f"Using LLM provider: {provider}, model: {model}")
```

**In memory/short_term.py**:
```python
logger = get_logger(__name__)
logger.info(f"Using SQLite checkpointer at {db_path}")
```

## ⚙️ Configuration

The observability package doesn't have direct configuration in `config.yaml`. Instead:
- Logging format and root level are hardcoded in `logger.py`
- Application loggers are always set to DEBUG level
- To change logging behavior, modify `educosys_claude/observability/logger.py`

### Current Hardcoded Configuration
```python
logging.basicConfig(
   level=logging.WARNING,     # Root logger level
   format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
```

### To Modify Logging Behavior
Edit `educosys_claude/observability/logger.py` to change:
1. Root logger level (currently `logging.WARNING`)
2. Log format string
3. Date format (by adding `datefmt` parameter to basicConfig)

## 🔄 Integration Points

The observability package is used by:
1. **Main Application** (`main.py`):
   - Logs startup, shutdown, and initialization events
   - Logs query handling and agent errors

2. **Agent Package**:
   - `agent/factory.py`: Logs LLM/provider selection
   - `agent/orchestrator.py`: Logs query handling and agent errors
   - `agent/tools.py`: Logs tool usage (especially search_codebase)

3. **Context Package**:
   - All indexers and retrievers: Log indexing and retrieval operations
   - `code_parser.py`: Log file parsing progress and errors

4. **LLM Package**:
   - `llm/factory.py`: Log LLM and embedder provider/model selection

5. **Memory Package**:
   - `memory/session.py`: Log session creation, resumption, and switching
   - `memory/short_term.py`: Log checkpointer database path

6. **Tools Package**:
   - `tools/filesystem_tools.py` and `tools/terminal_tools.py`: Log tool execution and errors

7. **MCP Package**:
  
```

**To Modify Logging Behavior**
Edit `educosys_claude/observability/logger.py` to change:
1. Root logger level (currently `logging.WARNING`)
2. Log format string
3. Date format (by adding `datefmt` parameter to basicConfig)

## 🔄 Integration Points

The observability package is used by:
1. **Main Application** (`main.py`):
   - Logs startup, shutdown, and initialization events
   - Logs query handling and agent errors

2. **Agent Package**:
   - `agent/factory.py`: Logs LLM/provider selection
   - `agent/orchestrator.py`: Logs query handling and agent errors
   - `agent/tools.py`: Logs tool usage (especially search_codebase)

3. **Context Package**:
   - All indexers and retrievers: Log indexing and retrieval operations
   - `code_parser.py`: Log file parsing progress and errors

4. **LLM Package**:
   - `llm/factory.py`: Log LLM and embedder provider/model selection

5. **Memory Package**:
   - `memory/session.py`: Log session creation, resumption, and switching
   - `memory/short_term.py`: Log checkpointer database path

6. **Tools Package**:
   - `tools/filesystem_tools.py` and `tools/terminal_tools.py`: Log tool execution and errors

7. **MCP Package**:
   - `mcp/educosys_mcp_client.py`: Log MCP server connections and tool loading
   - `mcp/educosys_mcp_config.py`: Log configuration loading (if any)

## 📊 Log Output Example

```
2026-07-04 10:30:45,123 | INFO | educosys_claude.main | Starting Educosys Claude
2026-07-04 10:30:45,124 | INFO | educosys_claude.llm.factory | Using LLM provider: openai, model: gpt-4o
2026-07-04 10:30:45,125 | INFO | educosys_claude.llm.factory | Using embeddings provider Mohit: openai, model: text-embedding-3-small
2026-07-04 10:30:45,126 | INFO | educosys_claude.context.indexers.factory | Loaded existing index with 1542 chunks
2026-07-04 10:30:45,127 | INFO | educosys_claude.memory.session | Resumed session: a1b2c3d4-e5f6-7890-g1h2-i3j4k5l6m7n8
2026-07-04 10:30:45,128 | INFO | educosys_claude.main | Educosys Claude[/bold blue] — RAG-powered code assistant
2026-07-04 10:30:45,129 | INFO | educosys_claude.main | Type [bold]'/exit'[/bold] to quit
```

## 🛠️ Customization

To customize logging for different environments:

### Development (More Verbose)
```python
# In logger.py - for development
logging.basicConfig(
   level=logging.INFO,  # Show more info
   format="%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s",
)
```

### Production (Less Verbose)
```python
# In logger.py - for production
logging.basicConfig(
   level=logging.WARNING,  # Only warnings and errors
   format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
```

### With File Logging
```python
# In logger.py - to also log to file
logging.basicConfig(
   level=logging.WARNING,
   format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
   handlers=[
       logging.FileHandler("app.log"),
       logging.StreamHandler()
   ]
)
```

## 💡 Best Practices

1. **Use `__name__` for logger names**: This provides hierarchical logging and makes it easy to trace logs to specific modules
   ```python
   logger = get_logger(__name__)  # Best practice
   ```

2. **Log at appropriate levels**:
   - `DEBUG`: Detailed information, typically of interest only when diagnosing problems
   - `INFO`: Confirmation that things are working as expected
   - `WARNING`: An indication that something unexpected happened, or indicative of some problem in the near future
   - `ERROR`: Due to a more serious problem, the software has not been able to perform some function
   - `CRITICAL`: A serious error, indicating that the program itself may be unable to continue running

3. **Include context in logs**: When logging errors, include relevant context to aid debugging
   ```python
   logger.error(f"Failed to process file {file_path}: {e}", exc_info=True)
   ```

4. **Avoid logging sensitive information**: Never log API keys, passwords, or other sensitive data
   ```python
   # DON'T do this:
   logger.debug(f"API key: {api_key}")
   
   # DO this instead:
   logger.debug("API key configured (length: %d)", len(api_key) if api_key else 0)
   ```

5. **Use structured logging when possible**: For production systems, consider using JSON logging for easier parsing
   ```python
   # Format for JSON logging (would require additional setup)
   format='{"time": "%(asctime)s", "level": "%(levelname)s", "logger": "%(name)s", "message": "%(message)s"}'
   ```

## 🔧 Troubleshooting

### Common Issues
1. **Not seeing debug logs**:
   - Ensure you're using `get_logger(__name__)` not just `get_logger("some_string")`
   - Remember that root logger is WARNING - only application loggers (via get_logger) show DEBUG
   - Check if logging is configured before any logs are emitted

2. **Too much noise from third-party libraries**:
   - The current configuration intentionally sets root to WARNING to suppress this
   - If you need to see specific library logs, you can adjust individually:
     ```python
     logging.getLogger("openai").setLevel(logging.INFO)
     ```

3. **Logs not appearing in expected location**:
   - Verify logging is configured early in application startup
   - Check for multiple basicConfig calls (only first one takes effect)
   - Ensure no handlers are being removed elsewhere in code

4. **Performance impact of logging**:
   - DEBUG logging can impact performance in tight loops
   - Consider guarding expensive log operations:
     ```python
     if logger.isEnabledFor(logging.DEBUG):
         logger.debug("Expensive operation: %s", expensive_computation())
     ```

### Best Practices for Debugging
1. **To troubleshoot indexing issues**: Look for logs from `educosys_claude.context.indexers.*`
2. **To troubleshoot retrieval issues**: Look for logs from `educosys_claude.context.retrievers.*`
3. **To troubleshoot agent issues**: Look for logs from `educosys_claude.agent.*`
4. **To troubleshoot LLM issues**: Look for logs from `educosys_claude.llm.factory`