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

**Purpose**: Creates and configures the LangChain agent with tools, memory, and system prompt.

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
  - **Human-in-the-Loop (HITL) Middleware**: Pauses execution for dangerous tools awaiting approval

**Human-in-the-Loop Middleware**:
```python
# Configured in factory.py - tools requiring approval
interrupt_on = {
    "run_command": {"allowed_decisions": ["approve", "edit", "reject"]},
    "run_in_directory": {"allowed_decisions": ["approve", "edit", "reject"]},
    "write_file": {"allowed_decisions": ["approve", "edit", "reject"]},
    "append_file": {"allowed_decisions": ["approve", "edit", "reject"]},
    # All GitHub MCP tools (create_pull_request, push_files, etc.)
}

# Middleware stack (ORDER MATTERS):
middleware = [
    PatchToolCallsMiddleware(),      # Repairs orphaned tool_calls after HITL resume
    HumanInTheLoopMiddleware(interrupt_on=interrupt_on),
]
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
- `ApprovalRequest` — dataclass for pending approval (thread_id, tool_name, tool_args, allowed_decisions, etc.)
- `GitHubApprovalStore` — persistence layer (Issue Comments or Gist backend)
- `GitHubActionsHITL` — main handler: interrupt → post to GitHub → poll → resume

**Usage in Workflow**:
```yaml
jobs:
  agent:
    runs-on: ubuntu-latest
    permissions:
      issues: write
    steps:
      - uses: actions/checkout@v4
      - name: Run agent with HITL
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}
        run: python -m educosys_claude.agent.hitl_github_actions
```

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