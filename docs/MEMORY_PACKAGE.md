# 💾 Memory Package

The `memory` package handles session management and conversation history persistence. It provides short-term memory with automatic summarization to manage context windows effectively, ensuring the agent can maintain conversation coherence over extended interactions.

## 📁 Package Structure

```
educosys_claude/memory/
├── __init__.py
├── session.py          # Session persistence and management
└── short_term.py       # Short-term memory with summarization
```

## 🧩 Components

### 1. Session Management (`session.py`)

**Purpose**: Manages persistent session IDs across application restarts, allowing users to resume conversations.

**Key Functions**:
- `get_current_session() -> str`: Retrieves existing session ID or creates a new one
- `new_session() -> str`: Creates and stores a new session ID
- `switch_session(session_id: str) -> str`: Switches to an existing session

**How It Works**:
1. Uses a file-based store (`.memory/current_session`) to persist the current session ID
2. On startup, checks for existing session file
3. If exists, reads and returns the session ID
4. If not, creates a new UUID-based session ID and stores it
5. Provides switching capability for multi-session workflows

**Session Storage**:
- File: `.memory/current_session` (relative to project root)
- Format: Plain text containing UUID string
- Directory: Created automatically if missing

### 2. Short-Term Memory (`short_term.py`)

**Purpose**: Implements LangChain's `SummarizationMiddleware` to automatically summarize conversation history when it exceeds token limits, preserving essential context while managing LLM context window constraints.

**Key Functions**:
- `get_checkpointer_db_path() -> str`: Returns path to SQLite database for LangGraph checkpointer
- `get_summarization_middleware() -> SummarizationMiddleware`: Configures and returns the summarization middleware

**How It Works**:
1. Uses SQLite database (`.memory/memory.db`) to persist chat history
2. When message count or token count exceeds threshold:
   - Takes oldest messages
   - Summarizes them using the LLM
   - Stores summary and keeps recent messages
3. Configuration controls:
   - `summarize_at_tokens`: Token threshold to trigger summarization
   - `keep_last_messages`: Number of recent messages to preserve verbatim

## 🔧 How It Works Together

### Session Flow
```
Application Start
     ↓
main.py -> get_current_session()
     ↓
memory/session.py:get_current_session()
     ↓
  Check for .memory/current_session file
     ↓
  If exists: read and return session ID
     ↓
  If not: generate UUID, save to file, return ID
     ↓
Return session ID to main.py for agent checkpointer
```

### Memory Management Flow
```
Conversation Turn
     ↓
agent.ainvoke() with thread_id (session ID)
     ↓
LangGraph checkpointer saves state to SQLite
     ↓
When message threshold reached:
     ↓
SummarizationMiddleware triggered
     ↓
  1. Extract oldest messages exceeding threshold
     ↓
  2. Pass to LLM for summarization (using get_llm())
     ↓
  3. Store summary in state
     ↓
  4. Keep most recent N messages verbatim
     ↓
Continue with summarized + recent messages
```

## ⚙️ Configuration

Memory behavior is configured in `educosys_claude/config.yaml`:

```yaml
memory:
  db_path: .memory/memory.db           # SQLite database path
  summarize_at_tokens: 4000            # Trigger summarization at this token count
  keep_last_messages: 20               # Keep this many recent messages verbatim
```

### Configuration Guidelines
- **summarize_at_tokens**: Set based on your LLM's context window
  - For 8K models: 4000-6000 (leave room for response)
  - For 16K models: 8000-12000
  - For 32K models: 16000-24000
- **keep_last_messages**: Number of recent exchanges to keep in full detail
  - Typical range: 5-20 (each exchange = user + assistant message)
  - Higher values preserve more detail but use more tokens

## 📝 Usage Examples

### Session Management
```python
from educosys_claude.memory.session import get_current_session, new_session, switch_session

# Get or create session
session_id = get_current_session()
print(f"Current session: {session_id}")

# Force new session
new_id = new_session()
print(f"Started new session: {new_id}")

# Switch to existing session
switched_id = switch_session("existing-uuid-here")
print(f"Switched to session: {switched_id}")
```

### Memory Middleware
```python
from educosys_claude.memory.short_term import get_summarization_middleware
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

# Get checkpointer path
db_path = get_checkpointer_db_path()
print(f"Using database: {db_path}")

# Get summarization middleware
summarization = get_summarization_middleware()
# Used in agent.checkpointer configuration
```

### Integration in Main Application
```python
# In educosys_claude/main.py
from educosys_claude.memory.short_term import get_checkpointer_db_path
from educosys_claude.memory.session import get_current_session
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

async def _run_async():
    # Get database path for checkpointer
    db_path = get_checkpointer_db_path()
    
    # Create checkpointer with persistence
    async with AsyncSqliteSaver.from_conn_string(db_path) as checkpointer:
        # Get current session ID
        session_id = get_current_session()
        
        # Initialize agent with checkpointer and session
        llm, embedder, index, agent, session_id = await initialize(checkpointer)
        # ... rest of initialization
```

## 🔄 Integration Points

The memory package is used by:
1. **Main Application**: For session management and checkpointer setup (`main.py`)
2. **Agent Package**: Through the checkpointer passed to `build_agent()` for persistent state
3. **LLM Package**: The summarization middleware uses `get_llm()` to generate summaries

## 📊 Performance Characteristics

- **Storage**: SQLite database (.memory/memory.db) - efficient for conversation history
- **Summarization Overhead**: Occurs when threshold is reached, uses LLM to condense history
- **Latency**: Minimal overhead for storage; summarization adds latency proportional to summary length
- **Scalability**: Designed for single-user sessions; scales with conversation length, not user count

## 🛠️ Customization Options

### Adjusting Summarization Behavior
Modify these in `config.yaml`:
```yaml
memory:
  # Increase for longer conversations before summarizing
  summarize_at_tokens: 6000  
  
  # Decrease to keep more verbatim history (increases token usage)
  keep_last_messages: 15
```

### Custom Summarization Prompt
To customize how conversations are summarized, you would need to extend or replace the `SummarizationMiddleware` with a custom implementation that uses a different prompt template.

## 💡 Best Practices

1. **Session Management**:
   - Sessions persist until the `.memory/current_session` file is deleted
   - To start fresh: delete the session file or use `/new_session` command
   - Multiple sessions can be managed manually via `/switch <session_id>`

2. **Memory Tuning**:
   - Monitor token usage with your LLM provider's dashboard
   - Adjust `summarize_at_tokens` to stay well below your model's context limit
   - Increase `keep_last_messages` if recent context is critical for your use case

3. **Storage Considerations**:
   - The `.memory` directory should be backed up if session persistence is important
   - SQLite database can grow large over very long conversations - consider periodic cleanup
   - In production, consider monitoring database size and implementing archival strategies

## 🔧 Troubleshooting

### Common Issues
- **"Database is locked" errors**: Usually caused by multiple processes accessing the same SQLite database. Ensure only one instance runs per directory.
- **Summarization not triggering**: Check that `summarize_at_tokens` is set appropriately and that conversations are actually reaching the threshold.
- **Lost sessions**: Verify the `.memory` directory is writable and not being cleared between runs.

### Performance Tuning
If summarization happens too frequently:
1. Increase `summarize_at_tokens`
2. Consider using a model with larger context window
3. Increase `keep_last_messages` if you need more recent verbatim context

If summarization affects response quality:
1. Decrease `summarize_at_tokens` to summarize less frequently
2. Increase `keep_last_messages` to preserve more recent context
3. Consider tuning the summarization prompt (requires code modification)