# 🤖 Agent Package

The `agent` package is responsible for creating and managing the AI agent that processes user queries, searches the codebase, and generates responses. It uses LangChain's agent framework with persistent memory and a curated set of tools.

## 📁 Package Structure

```
educosys_claude/agent/
├── __init__.py
├── factory.py                   # Agent creation and configuration
├── orchestrator.py              # Query handling entry point
├── tools.py                     # Custom agent tools (search_codebase)
├── hitl_github_actions.py       # GitHub Actions HITL integration
```

## 🧩 Components

### 1. Factory (`factory.py`)

**Purpose**: Creates and configures the LangChain agent with tools, memory, system prompt, and middleware stack.

**Key Functions**:
- `build_agent(checkpointer)`: Creates a LangChain agent with:
  - LLM from `llm.factory.get_llm()`
  - Tools including:
    - `search_codebase` (custom tool for querying the codebase)
    - Terminal tools (`run_command`, `run_in_directory`)
    - Filesystem tools (`read_file`, `write_file`, `append_file`, `delete_file`, `list_directory`, `file_exists`)
    - MCP tools from configured servers
  - System prompt that instructs the agent to:
    - Always use `search_codebase` before answering
    - Reference specific file names, function names, and line numbers
    - Admit when answers aren't found in the codebase
  - Persistent checkpointer for session memory
  - **Middleware Stack** (8 layers, order matters — inner wraps outer):

**Middleware Stack (inner → outer):**
```python
middleware = [
    ModelCallLimitMiddleware(),      # 1. Budget control — max calls per thread/run
    ModelRetryMiddleware(),          # 2. Retry failed model calls with backoff
    ModelFallbackMiddleware(),       # 3. Fallback to alt models on failure
    ToolRetryMiddleware(),           # 4. Retry failed tool calls
    PIIMiddleware(),                 # 5. Detect/redact PII (email, SSN, API keys, tokens)
    ContentFilterMiddleware(),       # 6. Block prohibited content (violence, illegal, self-harm)
    HumanInTheLoopMiddleware(),      # 7. Pause for approval on dangerous tools
    SummarizationMiddleware(),       # 8. Compress history when token threshold exceeded (outermost)
]
```

**Why this order?**
1. **PII before Content Filter** — Redact sensitive data first so it doesn't trigger false positives in content filtering
2. **Both before HITL** — Clean data before human approval decision
3. **After retries** — Only process successful requests (retries handled first)
4. **Summarization outermost** — Wraps entire conversation; sees compressed history

**HITL Configuration** (tools requiring approval):
```python
interrupt_on = {
    "run_command": {"allowed_decisions": ["approve", "edit", "reject"]},
    "run_in_directory": {"allowed_decisions": ["approve", "edit", "reject"]},
    "write_file": {"allowed_decisions": ["approve", "edit", "reject"]},
    "append_file": {"allowed_decisions": ["approve", "edit", "reject"]},
    # All GitHub MCP tools (create_pull_request, push_files, etc.)
}
```

**System Prompt**:
```
You are a senior software engineer with deep knowledge of the codebase.
Always use the search_codebase tool before answering any question.
Reference specific file names, function names and line numbers in your answers.
If you cannot not find the answer in the codebase, say so explicitly.
```

### 2. Orchestrator (`orchestrator.py`)

**Purpose**: Entry point for all user queries - invokes the agent with session management.

**Key Functions**:
- `handle_query(agent, question: str, thread_id: str) -> str`:
  - Takes an agent, user question, and session ID
  - Configures the agent with the session thread ID
  - Invokes the agent asynchronously
  - **Auto-detects GitHub Actions environment** and routes to appropriate HITL handler
  - Returns the agent's response or error message
  - Logs query handling for observability

**HITL Routing Logic**:
```python
if GITHUB_ACTIONS == "true" and HITL_GITHUB_AVAILABLE:
    return await handle_query_github_hitl(agent, question, thread_id)
# else: local rich.Prompt for terminal approval
```

### 3. Tools (`tools.py`)

**Purpose**: Defines custom tools available to the agent, primarily for codebase search.

**Key Tools**:
- `search_codebase(query: str) -> str`:
  - Searches the indexed codebase for relevant code chunks
  - Uses the retriever from `context.retrievers.factory.get_retriever()`
  - Returns top-k chunks (default k=5) with file/line info, type, content, relevance score

### 4. GitHub Actions HITL (`hitl_github_actions.py`)

**Purpose**: Provides GitHub Actions-compatible Human-in-the-Loop approval mechanisms.

**Problem**: Local terminal `rich.Prompt` blocks indefinitely in CI (no TTY).

**Three Approaches**:

| Approach | Mechanism | Best For |
|----------|-----------|----------|
| **Environment Protection Rules** | Workflow pauses at `environment: production`; reviewers click Approve/Reject in GitHub UI | Production deployments, compliance |
| **PR/Issue Comment Polling** | Bot posts approval request as comment; polls for `/APPROVE`, `/REJECT`, `/EDIT` replies | General CI, standard GITHUB_TOKEN |
| **GitHub Gist** | Private gist stores approval state; polls for updates | Fork PRs, minimal permissions |

**Key Classes**:
- `ApprovalRequest` — dataclass for pending approval
- `GitHubApprovalStore` — persistence layer (Issue Comments or Gist backend)
- `GitHubActionsHITL` — main handler: interrupt → post to GitHub → poll → resume

**Documentation**: See [HITL_GITHUB_ACTIONS.md](HITL_GITHUB_ACTIONS.md) for complete workflow setup, configuration, and troubleshooting.

### 5. Usage in `main.py`
```python
from educosys_claude.agent.orchestrator import handle_query

# Auto-detects GitHub Actions vs local terminal
response = await handle_query(agent, question, thread_id)
```

## 🔄 Data Flow

```
User Query
     ↓
/main.py (REPL)
     ↓
/agent/orchestrator.py::handle_query()
     ↓
┌─────────────────────────────────────┐
│        HITL Detection               │
│  GITHUB_ACTIONS=true? → GitHub HITL │
│  else → Terminal Prompt             │
└─────────────────────────────────────┘
     ↓
Agent (from factory.py) with tools
     ↓
Agent decides to use search_codebase tool
     ↓
/agent/tools.py::search_codebase()
     ↓
/context/retrievers/factory.py:get_retriever()
     ↓
/context/retrievers/*_qdrant.py or *_chroma.py
     ↓
Vector store search (Qdrant/ChromaDB)
     ↓
Return formatted code chunks
     ↓
Agent uses chunks + LLM to generate response
     ↓
Response returned to user
```

## ⚙️ Configuration

- **LLM/Embeddings**: `config.yaml` via `llm.factory`
- **Retrieval mode**: `rag.mode` (hybrid/vector/keyword)
- **Vector store**: `vector_store.provider` (Qdrant/ChromaDB/Elasticsearch)
- **MCP servers**: `educosys_mcp_servers.json`
- **HITL tools**: `factory.py` `interrupt_on` dict
- **Memory**: `memory.db_path`, `summarize_at_tokens`, `keep_last_messages`

## 📝 Usage Examples

The agent can answer:
- "How does the authentication system work?"
- "Show me the main entry point of the application"
- "What functions are available in the utils module?"
- "Explain the data flow for processing a user query"

Each answer includes specific references to files, functions, and line numbers from the codebase.