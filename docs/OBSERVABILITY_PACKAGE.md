# 👁️ Observability Package

The `observability` package provides structured logging with rotating file output, per-handler log levels, and third-party library noise suppression.

## 📁 Package Structure

```
educosys_claude/observability/
├── __init__.py
└── logger.py           # Logging configuration and utility
```

## 🧩 Components

### Logger (`logger.py`)

**Purpose**: Configures application logging with:
- **Console handler**: INFO+ (clean output, less verbose)
- **Rotating file handler**: DEBUG+ (detailed debugging in file)
- **Root logger**: DEBUG (captures everything, handlers filter)
- **Application modules** (`educosys_claude.*`): DEBUG level
- **Third-party libraries**: WARNING+ (suppressed noise)

**Key Functions**:
- `setup_logging()`: Initialize logging from `config.yaml` (called at import)
- `get_logger(name: str) -> logging.Logger`: Get logger for module, auto-sets DEBUG for our modules

**Log Levels**:
| Logger | Level | Where |
|--------|-------|-------|
| Root | DEBUG | Captures all |
| Console handler | INFO | Terminal output |
| File handler | DEBUG | `.radha/logs/agent.log` |
| `educosys_claude.*` modules | DEBUG | Detailed tracing |
| Third-party (openai, httpx, langsmith, aiosqlite, etc.) | WARNING | Noise suppression |

## ⚙️ Configuration (`config.yaml`)

```yaml
logging:
  root_level: DEBUG           # Root logger level (DEBUG captures all)
  file_path: .radha/logs/agent.log
  max_bytes: 10485760         # 10MB per file
  backup_count: 5             # Keep 5 rotated files
  format: "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
  console: true               # Enable console output
```

## 🔧 How It Works

### Logging Initialization

```
Module Import (logger.py)
         ↓
setup_logging() called
         ↓
1. Read config.yaml logging section
2. Create RotatingFileHandler (DEBUG) + StreamHandler (INFO)
3. Set root logger to DEBUG
4. Suppress noisy third-party loggers to WARNING
5. Register formatters
         ↓
Application calls get_logger(__name__)
         ↓
Returns logger with DEBUG level for educosys_claude.* modules
```

### Usage in Application Code

```python
# At the top of each module
from educosys_claude.observability.logger import get_logger

# Create logger for this module
logger = get_logger(__name__)

# Then use throughout
logger.debug("Detailed debugging information")
logger.info("General operational information")
logger.warning("Warning about potential issues")
logger.error("Error that occurred", exc_info=True)
logger.critical("Critical error requiring immediate attention")
```

### Usage Across Layers

**In main.py**:
```python
logger = get_logger(__name__)
logger.info("Starting Educosys Claude")
```

**In agent/factory.py**:
```python
logger = get_logger(__name__)
logger.info(f"Using LLM provider: {provider}, model: {model}")
logger.info(f"Human-in-the-loop enabled for tools: {sorted(interrupt_on.keys())}")
```

**In memory/short_term.py**:
```python
logger = get_logger(__name__)
logger.info(f"Using SQLite checkpointer at {db_path}")
```

## 📝 Log Output Examples

### Console (INFO+)

```
2026-07-11 14:30:49 | INFO     | educosys_claude.test | INFO - this should be in console and file
2026-07-11 14:30:49 | WARNING  | educosys_claude.test | WARNING - this should be in console and file
```

### File (DEBUG+)

```
2026-07-11 14:30:49 | DEBUG    | educosys_claude.test | DEBUG - this should be in file only
2026-07-11 14:30:49 | INFO     | educosys_claude.test | INFO - this should be in console and file
2026-07-11 14:30:49 | WARNING  | educosys_claude.test | WARNING - this should be in console and file
```

## 🔄 Integration Points

The observability package is used by:

1. **Main Application** (`main.py`): Startup, shutdown, query handling
2. **Agent Package**: Factory, orchestrator, tools, HITL middleware
3. **Context Package**: Indexers, retrievers, code parser
4. **LLM Package**: LLM and embedder factory
5. **Memory Package**: Session, short-term (checkpointer), long-term (fact extraction)
6. **Tools Package**: Filesystem, terminal operations
7. **MCP Package**: Server connections, tool loading

## 🛠️ Customization

### Change Log Levels via Config

```yaml
# config.yaml
logging:
  root_level: DEBUG
  file_path: .radha/logs/agent.log
  max_bytes: 10485760
  backup_count: 5
  format: "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
  console: true
```

### Suppress/Unsuppress Specific Libraries

```python
import logging

# In your code, adjust individual library loggers
logging.getLogger("openai").setLevel(logging.INFO)      # See OpenAI requests
logging.getLogger("httpx").setLevel(logging.DEBUG)      # See HTTP traffic
logging.getLogger("chromadb").setLevel(logging.WARNING) # Suppress ChromaDB
```

### Add Custom Handlers

```python
import logging
from educosys_claude.observability.logger import setup_logging

setup_logging()

# Add syslog, JSON file, etc.
json_handler = logging.FileHandler(".radha/logs/agent.json")
json_handler.setFormatter(logging.Formatter('{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}'))
logging.getLogger().addHandler(json_handler)
```

## 💡 Best Practices

1. **Use `__name__` for logger names**: Hierarchical, traceable to module
2. **Log at appropriate levels**:
   - `DEBUG`: Detailed tracing (file only)
   - `INFO`: Confirmation of normal operation
   - `WARNING`: Unexpected but handled
   - `ERROR`: Operation failed
   - `CRITICAL`: Program may not continue
3. **Include context**: `logger.error(f"Failed to process {file}: {e}", exc_info=True)`
4. **Never log secrets**: Use `logger.debug("API key length: %d", len(key))` not the key itself
5. **Guard expensive logging**:
   ```python
   if logger.isEnabledFor(logging.DEBUG):
       logger.debug("Expensive: %s", expensive_computation())
   ```

## 🔧 Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| No DEBUG in console | Console handler at INFO | Check file for DEBUG; change console handler level if needed |
| No file if required |
| Too much noise | Missing third-party suppression | Add to suppression list in `logger.py` |
| Log file not rotating | `max_bytes`/`backup_count` | Check config values; ensure handler is `RotatingFileHandler` |
| Logs not appearing | `setup_logging()` not called | Import `educosys_claude.observability.logger` early (main.py does this) |
| Double logging | Multiple handlers added | `root_logger.handlers.clear()` in setup_logging prevents this |

### Debug Logger Configuration

```python
import logging
root = logging.getLogger()
print("Root level:", root.level)
for i, h in enumerate(root.handlers):
    print(f"Handler {i}: {type(h).__name__}, level={h.level}")
```

## 📊 Log File Location

- **Path**: `.radha/logs/agent.log` (configurable)
- **Rotation**: 10MB per file, 5 backups = max ~50MB
- **Encoding**: UTF-8
- **View**: `tail -f .radha/logs/agent.log` or open in editor