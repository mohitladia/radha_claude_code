# 🤖 Agent Package

The `agent` package is responsible for creating and managing the AI agent that processes user queries, searches the codebase, and generates responses. It uses LangChain's agent framework with persistent memory and a curated set of tools.

## 📁 Package Structure

```
educosys_claude/agent/
├── __init__.py
├── factory.py          # Agent creation and configuration
├── orchestrator.py     # Query handling entry point
└── tools.py            # Custom agent tools (search_codebase)
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
  - Returns the agent's response or error message
  - Logs query handling for observability

### 3. Tools (`tools.py`)

**Purpose**: Defines custom tools available to the agent, primarily for codebase search.

**Key Tools**:
- `search_codebase(query: str) -> str`:
  - Searches the indexed codebase for relevant code chunks
  - Uses the retriever from `context.retrievers.factory.get_retriever()`
  - Returns top-k chunks (default k=5) with:
    - File name and line numbers
    - Code chunk type (function, class, block)
    - Actual code content
    - Relevance score
  - Formats results as a readable string with clear separation between chunks
  - Returns "No relevant code found." if no matches

## 🔧 How It Works Together

1. **Initialization** (in `main.py`):
   - Agent is built using `build_agent()` with a checkpointer for memory
   - LLM, embedder, and index are initialized
   - Session is retrieved or created

2. **Query Processing** (in `main.py` -> `orchestrator.py`):
   - User input is received via the REPL
   - Commands like `/ask <question>` are parsed
   - Questions are sent to `handle_query()` in the orchestrator
   - Orchestrator invokes the agent with session context
   - Agent uses tools (especially `search_codebase`) to find relevant code
   - Agent generates response using LLM with codebase context
   - Response is returned to user

3. **Tool Usage** (in `agent/tools.py`):
   - When agent decides to search, it calls `search_codebase`
   - Tool uses retriever to find relevant code chunks from vector store
   - Results are formatted and returned to agent
   - Agent incorporates code chunks into its reasoning and response generation

## 🔄 Data Flow

```
User Query
     ↓
/main.py (REPL)
     ↓
/agent/orchestrator.py::handle_query()
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

The agent's behavior is influenced by configuration in `config.yaml`:
- LLM provider and model (via `llm.factory`)
- Embedding provider and model (via `llm.factory.get_embedder()`)
- Retrieval mode (hybrid/vector/keyword) affects search results
- Vector store provider (Qdrant/ChromaDB/Elasticsearch) affects search implementation
- MCP server configuration affects available tools

## 📝 Usage Examples

The agent can be used to answer questions like:
- "How does the authentication system work?"
- "Show me the main entry point of the application"
- "What functions are available in the utils module?"
- "Explain the data flow for processing a user query"

Each answer will include specific references to files, functions, and line numbers from the codebase.