# 💾 Memory Package

The `memory` package handles session management and conversation history persistence. It provides:

- **Short-term memory**: Automatic summarization to manage context windows
- **Long-term memory**: Vector-based fact extraction for persistent knowledge across sessions
- **Session management**: UUID-based conversation threads

## 📁 Package Structure

```
educosys_claude/memory/
├── __init__.py
├── session.py              # Session persistence and management
├── short_term.py           # Short-term memory with summarization
└── long_term.py            # Long-term memory (fact extraction + vector store)
```

---

## 🧩 Components

### 1. Session Management (`session.py`)

**Purpose**: Manages persistent session IDs across application restarts.

**Key Functions**:
- `get_current_session() -> str`: Retrieves existing session ID or creates new one
- `new_session() -> str`: Creates and stores a new session ID
- `switch_session(session_id: str) -> str`: Switches to an existing session

**How It Works**:
1. Uses `.memory/current_session` file to persist current session ID
2. On startup, checks for existing session file
3. If exists, reads and returns the session ID
4. If not, creates new UUID-based session ID and stores it

**Code Reference**: `educosys_claude/memory/session.py`

```python
# Session file location
SESSION_FILE = Path(".memory/current_session")

def get_current_session() -> str:
    """Get current session ID, creating one if needed."""
    if SESSION_FILE.exists():
        return SESSION_FILE.read_text().strip()
    return new_session()

def new_session() -> str:
    """Create and persist new session ID."""
    session_id = str(uuid.uuid4())
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(session_id)
    return session_id

def switch_session(session_id: str) -> str:
    """Switch to existing session."""
    SESSION_FILE.write_text(session_id)
    return session_id
```

---

### 2. Short-Term Memory (`short_term.py`)

**Purpose**: Implements LangChain's `SummarizationMiddleware` to automatically summarize conversation history when it exceeds token limits.

**Key Functions**:
- `get_checkpointer_db_path() -> str`: SQLite database path for LangGraph checkpointer
- `get_checkpointer() -> AsyncSqliteSaver`: Creates checkpointer instance
- `get_summarization_middleware() -> SummarizationMiddleware`: Configured summarization middleware

**How It Works**:
1. Uses SQLite (`.memory/memory.db`) to persist chat history via LangGraph checkpointer
2. When message count/token count exceeds threshold:
   - Takes oldest messages exceeding threshold
   - Summarizes them using LLM
   - Stores summary + keeps recent messages verbatim
3. Config: `summarize_at_tokens` (trigger threshold), `keep_last_messages` (verbatim retention)

**Configuration** (`config.yaml`):
```yaml
memory:
  db_path: .memory/memory.db              # SQLite for short-term checkpointer
  summarize_at_tokens: 4000               # Trigger summarization
  keep_last_messages: 20                  # Verbatim retention
```

**Short-Term Memory Flow**:
```
User sends message
       ↓
Agent invoked with thread_id (session ID)
       ↓
Graph executes → messages accumulated in state
       ↓
Checkpointer saves state to SQLite after each step
       ↓
SummarizationMiddleware checks token count
       ↓
If > summarize_at_tokens:
   → Extract messages[0:-keep_last_messages]
   → Call LLM: "Summarize this conversation..."
   → Replace with SystemMessage(summary) + recent messages
       ↓
Response returned
```

**Code Reference**: `educosys_claude/memory/short_term.py`

```python
def get_checkpointer_db_path() -> str:
    """Return SQLite path for LangGraph checkpointer."""
    db_dir = Path(config["memory"]["db_path"]).parent
    db_dir.mkdir(parents=True, exist_ok=True)
    return str(Path(config["memory"]["db_path"]).resolve())

def get_checkpointer() -> AsyncSqliteSaver:
    """Create async SQLite checkpointer for state persistence."""
    db_path = get_checkpointer_db_path()
    return AsyncSqliteSaver.from_conn_string(db_path)

def get_summarization_middleware() -> SummarizationMiddleware:
    """Configure summarization middleware for context compression."""
    llm = get_llm()
    return SummarizationMiddleware(
        llm=llm,
        summarize_at_tokens=config["memory"]["summarize_at_tokens"],
        keep_last_messages=config["memory"]["keep_last_messages"],
    )
```

**Integration in Agent Factory** (`agent/factory.py`):
```python
checkpointer = get_checkpointer()
summarization_middleware = get_summarization_middleware()

agent = create_agent(
    llm=llm,
    tools=tools,
    system_prompt=prompt,
    checkpointer=checkpointer,
    middleware=[
        PatchToolCallsMiddleware(),  # Must run FIRST on resume
        HumanInTheLoopMiddleware(interrupt_on=DANGEROUS_TOOLS),
        summarization_middleware,    # Runs after HITL on normal flow
    ],
)
```

**Middleware Order Matters**:
- On **normal execution**: Order doesn't matter much
- On **HITL resume**: `PatchToolCallsMiddleware` MUST be first to clean orphaned `tool_calls` from AIMessage before `SummarizationMiddleware` sees them

---

### 2.1 Short-Term Memory Deep Dive

#### Checkpointer — What Gets Saved

**SQLite table**: `checkpoints`

| Column | Value |
|--------|-------|
| `thread_id` | Session UUID (e.g., `a1b2-c3d4`) |
| `checkpoint_ns` | Namespace (usually empty) |
| `checkpoint` | JSON blob: `{ "messages": [...], "other_state": ... }` |
| `parent_checkpoint_id` | Previous checkpoint ID (for history) |

**Every graph step** → new checkpoint row. Full message history persisted.

#### SummarizationMiddleware — Internal Logic

```python
# langgraph/prebuilt/memory.py (simplified)
class SummarizationMiddleware:
    def __init__(self, llm, summarize_at_tokens, keep_last_messages):
        self.llm = llm
        self.summarize_at_tokens = summarize_at_tokens
        self.keep_last_messages = keep_last_messages

    async def on_step_end(self, state, config):
        messages = state["messages"]
        token_count = count_tokens(messages)
        
        if token_count > self.summarize_at_tokens:
            # 1. Split messages
            to_summarize = messages[:-self.keep_last_messages]
            keep = messages[-self.keep_last_messages:]
            
            # 2. Call LLM to summarize
            summary_prompt = f"""Summarize the following conversation concisely.
            Focus on key facts, decisions, and context needed for continuation.
            
            Conversation:
            {format_messages(to_summarize)}"""
            
            summary = await self.llm.ainvoke([HumanMessage(content=summary_prompt)])
            
            # 3. Replace old messages with summary + recent
            new_messages = [
                SystemMessage(content=f"Conversation summary: {summary.content}"),
                *keep
            ]
            
            # 4. Update state IN PLACE
            state["messages"] = new_messages
```

#### Execution Timeline (Single `ainvoke()` Call)

```
User: "Fix the auth bug"
         │
         ▼
agent.ainvoke({messages: [HumanMessage("Fix the auth bug")]}, 
              config={thread_id: "abc-123"}, version="v2")
         │
         ▼
┌────────────────────────────────────────────────────────────┐
│ STEP 1: LOAD STATE                                          │
│ checkpointer.get_tuple(config)                              │
│ → Returns Checkpoint with messages from LAST turn          │
│ → If summarized before: SystemMessage(summary) + recent    │
└────────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────┐
│ STEP 2: GRAPH EXECUTES                                      │
│ ┌─────────────┐   ┌─────────────┐   ┌─────────────┐        │
│ │ Node: LLM   │→  │ Node: Tool  │→  │ Node: LLM   │        │
│ │ (thinks)    │   │ (runs cmd)  │   │ (responds)  │        │
│ └─────────────┘   └─────────────┘   └─────────────┘        │
│       │               │               │                      │
│       ▼               ▼               ▼                      │
│   AIMessage      ToolMessage      AIMessage                 │
│   (tool_calls)   (result)         (final text)              │
└────────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────┐
│ STEP 3: AFTER EACH NODE → SummarizationMiddleware.on_step_end│
│                                                              │
│ Count tokens in state["messages"]                           │
│ If > 4000:                                                  │
│   → Summarize oldest (keep_last_messages=20)               │
│   → Replace with SystemMessage(summary) + last 20          │
└────────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────┐
│ STEP 4: CHECKPOINTER SAVES                                  │
│ checkpointer.put(config, checkpoint, metadata)             │
│ → New row in SQLite with UPDATED messages                  │
└────────────────────────────────────────────────────────────┘
         │
         ▼
Return final state to user
```

#### What the LLM Actually Sees (Example)

**Turn 1** (fresh session):
```
messages = [HumanMessage("Fix auth bug")]
```

**Turn 5** (after 4 turns, 5000 tokens):
```
messages = [
    SystemMessage("Conversation summary: User asked to fix JWT auth bug in FastAPI.
                    Identified issue in middleware token validation. 
                    Applied fix: added leeway for clock skew. Tests pass."),
    HumanMessage("Also check refresh token rotation"),
    AIMessage("Fixed refresh token rotation..."),
    ToolMessage("test output..."),
    HumanMessage("Good, now add tests"),
    AIMessage("Adding tests..."),
    # ... last 20 messages verbatim
]
```

**Turn 10** (after more turns):
```
messages = [
    SystemMessage("Conversation summary: User fixed JWT auth bug, added refresh 
                    token rotation, wrote tests. Now working on rate limiting."),
    # ... last 20 messages
]
```

#### Token Counting

```python
# In SummarizationMiddleware (langgraph internal)
def count_tokens(messages: List[BaseMessage]) -> int:
    # Uses tiktoken for OpenAI models, approx for others
    total = 0
    for msg in messages:
        total += len(msg.content) // 4  # rough approximation
        if hasattr(msg, 'tool_calls'):
            total += sum(len(json.dumps(tc)) for tc in msg.tool_calls) // 4
    return total
```

Config in `config.yaml`:
```yaml
memory:
  summarize_at_tokens: 4000    # Trigger threshold
  keep_last_messages: 20       # Keep verbatim
```

#### Critical: Middleware Order for HITL

```python
# agent/factory.py
middleware = [
    PatchToolCallsMiddleware(),           # 1st: MUST run first on resume
    HumanInTheLoopMiddleware(...),        # 2nd: pauses for dangerous tools
    summarization_middleware,             # 3rd: compresses history
]
```

**Why order matters on resume:**

```
HITL RESUME FLOW:
──────────────────────────────────────────────────────────────
1. User approves → agent.ainvoke(Command(resume={...}), version="v2")
    │
2. Graph loads checkpoint (has AIMessage with tool_calls, NO ToolMessage)
    │
3. PatchToolCallsMiddleware.on_step_start() runs FIRST
    │   → Sees AIMessage with tool_calls but no responses
    │   → Clears tool_calls or injects dummy ToolMessages
    │   → State now "clean"
    │
4. HumanInTheLoopMiddleware.on_step_start()
    │   → Sees clean state, no interrupts needed
    │
5. SummarizationMiddleware.on_step_end()
    │   → Sees clean messages, counts tokens correctly
    │
6. Normal execution continues
```

**If order wrong** (summarization before patch):
- Summarization sees orphaned `tool_calls` → token count inflated
- May trigger unnecessary summarization
- Or worse: LLM summarizes broken state

#### Session Persistence

```
.memory/
├── current_session          # "a1b2c3d4-uuid" — current thread_id
└── memory.db                # SQLite with all checkpoints
```

```python
# memory/session.py
SESSION_FILE = Path(".memory/current_session")

def get_current_session() -> str:
    if SESSION_FILE.exists():
        return SESSION_FILE.read_text().strip()
    return new_session()

def new_session() -> str:
    sid = str(uuid.uuid4())
    SESSION_FILE.write_text(sid)
    return sid
```

**New session** → new `thread_id` → fresh checkpointer state (but long-term memory still accessible).

#### Debugging Commands

```bash
# View checkpoints for current session
sqlite3 .memory/memory.db "SELECT thread_id, checkpoint_id, parent_checkpoint_id 
                           FROM checkpoints 
                           WHERE thread_id = $(cat .memory/current_session);"

# View message count per checkpoint
sqlite3 .memory/memory.db "SELECT thread_id, json_array_length(json_extract(checkpoint, '$.messages'))
                           FROM checkpoints;"

# Inspect a specific checkpoint
sqlite3 .memory/memory.db "SELECT json_extract(checkpoint, '$.messages[0]') 
                           FROM checkpoints WHERE checkpoint_id = '...';"
```

---

### Summary Table

| Question | Answer |
|----------|--------|
| **Runs before model?** | No — runs **during** graph execution, after each node |
| **What triggers it?** | Token count > `summarize_at_tokens` (default 4000) |
| **What does LLM see?** | Summary + last N messages (default 20) |
| **Where stored?** | SQLite (`.memory/memory.db`) via checkpointer |
| **Survives restart?** | Yes — checkpointer loads last checkpoint |
| **New session = clean slate?** | Yes for short-term; long-term memory persists |
| **HITL resume safe?** | Yes — **if** `PatchToolCallsMiddleware` is FIRST |

---

### 3.1 Long-Term Memory Deep Dive

#### MemoryFact Lifecycle

```
EXTRACTION (LLM)
──────────────────────────────────────
{
  "id": "uuid4()",
  "content": "Project uses FastAPI with Pydantic v2",
  "category": "project_context",
  "confidence": 0.95,
  "source_thread_id": "abc-123",
  "created_at": "2026-07-11T10:30:00Z",
  "metadata": {"file_mentioned": "main.py"}
}
         │
         ▼
EMBEDDING (get_embedder())
──────────────────────────────────────
vector = embedder.embed_query(content)  # 1536-dim for OpenAI
         │
         ▼
VECTOR STORE (Qdrant/Chroma)
──────────────────────────────────────
collection: "user_memory"
point: {
  id: "uuid4()",
  vector: [...],
  payload: {
    "content": "...",
    "category": "project_context",
    "confidence": 0.95,
    "source_thread_id": "abc-123",
    "created_at": "2026-07-11T10:30:00Z",
    "metadata": {...}
  }
}
```

#### Query Flow Detail

```python
# ltm.get_context_for_query("How do I run tests?")
async def get_context_for_query(self, query: str, k: int = 5) -> str:
    # 1. Embed query
    query_vector = self.embedder.embed_query(query)
    
    # 2. Similarity search in "user_memory" collection
    results = await self.store.asimilarity_search_with_relevance_scores(
        query, k=k, filter=None
    )
    
    # 3. Filter by score
    facts = []
    for doc, score in results:
        if score < 0.3:  # min_score
            continue
        fact = MemoryFact.from_dict(json.loads(doc.page_content))
        facts.append(fact)
    
    # 4. Format for injection
    if not facts:
        return ""
    
    lines = ["=== Relevant Long-Term Memory ==="]
    for fact in facts:
        lines.append(f"- [{fact.category}] {fact.content} (confidence: {fact.confidence:.2f})")
    lines.append("")
    
    return "\n".join(lines)
```

#### Concrete Example

**Session 1 (Today):**
```
User: /ask "How do I run tests?"
Agent:  "Use pytest with -x flag. The project uses pytest-asyncio for async tests.
         Run: pytest tests/ -x -v"

User: /ask "What's the database?"
Agent:  "PostgreSQL with async SQLAlchemy 2.0. Connection string in config.yaml"
```

**Background extraction runs:**
```json
[
  {"content": "User prefers pytest with -x flag for fast failure", 
   "category": "preference", "confidence": 0.9},
  {"content": "Project uses PostgreSQL with async SQLAlchemy 2.0", 
   "category": "project_context", "confidence": 0.95},
  {"content": "Connection string stored in config.yaml", 
   "category": "project_context", "confidence": 0.8}
]
```

**Session 2 (Tomorrow):**
```
User: /ask "How do I run the test suite?"
```

**Before agent runs:**
1. `get_context_for_query("How do I run the test suite?")`
2. Embeds query → searches "user_memory" collection
3. Finds: "User prefers pytest with -x flag for fast failure" (score: 0.87)
4. Prepends to question:
```
=== Relevant Long-Term Memory ===
- [preference] User prefers pytest with -x flag for fast failure (confidence: 0.90)

User question: How do I run the test suite?
```
5. Agent answers: "Based on your preference, use `pytest -x` for fast failure..."
```

#### Why This Works Across Sessions

| Component | Persistence |
|-----------|-------------|
| **Short-term** | SQLite checkpointer (`.memory/memory.db`) — per `thread_id` |
| **Session ID** | `.memory/current_session` file — survives restarts |
| **Long-term** | Vector store (`user_memory` collection) — **no thread_id filter** |

The vector store query **doesn't filter by `thread_id`** — it searches all facts from all sessions. That's the point: facts learned in one session are available in the next.

#### Configuration & Tuning

```python
# In orchestrator.py - adjust retrieval
memory_context = await ltm.get_context_for_query(
    question,
    k=3,                    # How many facts to retrieve
    categories=["preference", "project_context"]  # Filter categories
)

# In long_term.py - adjust storage
await ltm.extract_and_store_facts(
    messages, 
    thread_id, 
    max_facts=10            # Limit facts per turn
)
```

#### What's NOT Done Yet

| Feature | Status |
|---------|--------|
| Fact deduplication (same fact extracted multiple times) | ❌ Not implemented — will create duplicates |
| Fact expiration / decay | ❌ Not implemented |
| Cross-fact reasoning (link related facts) | ❌ Not implemented |
| Manual fact correction via `/remember` command | ❌ Not implemented |
| Per-user isolation (multi-user) | ❌ Not implemented — shared for all sessions |

#### Debugging Commands

```python
# Check what's in long-term memory
from educosys_claude.memory import get_long_term_memory

ltm = get_long_term_memory()
facts = await ltm.retrieve_relevant("database", k=10, min_score=0.0)
for f in facts:
    print(f"[{f.category}] {f.content[:80]} (conf: {f.confidence})")
```

```bash
# Or via CLI
python -c "
import asyncio
from educosys_claude.memory import get_long_term_memory

async def check():
    ltm = get_long_term_memory()
    facts = await ltm.retrieve_relevant('', k=20, min_score=0.0)
    for f in facts:
        print(f'{f.category}: {f.content[:80]}')

asyncio.run(check())
"
```

---

**Purpose**: Extracts durable facts from conversations and stores them in a vector database for retrieval across sessions. Unlike short-term memory (which summarizes), long-term memory distills **specific, queryable facts**.

**Key Classes**:
- `MemoryFact` — dataclass representing a single extracted fact
- `LongTermMemory` — main class with extraction, storage, and retrieval

#### MemoryFact Schema

```python
@dataclass
class MemoryFact:
    id: str                          # UUID
    content: str                     # The fact itself (e.g., "Project uses FastAPI with SQLModel")
    category: str                    # "preference" | "pattern" | "fact" | "project_context"
    confidence: float                # 0.0 - 1.0 (LLM-assessed reliability)
    source_thread_id: str            # Session this fact came from
    created_at: str                  # ISO timestamp (auto-set)
    metadata: dict                   # Arbitrary extra data (file paths, tech stack, etc.)
```

**Category Values**:
| Category | Description | Examples |
|----------|-------------|----------|
| `preference` | User's coding style, tool preferences, workflow choices | "User prefers pytest with fixtures over unittest" |
| `pattern` | Recurring patterns in how they work or what they ask | "User often asks for tests before implementation" |
| `fact` | Concrete information about the project/team/environment | "Database is PostgreSQL 15" |
| `project_context` | Architectural decisions, tech stack, conventions | "Project uses FastAPI with async SQLAlchemy" |

#### LongTermMemory API

```python
from educosys_claude.memory import get_long_term_memory

ltm = get_long_term_memory()

# Retrieve relevant facts for a query (returns formatted context string)
context = await ltm.get_context_for_query("How do I run tests?")

# Manually extract & store facts from messages
await ltm.extract_and_store_facts(messages, thread_id="session-123")

# Retrieve raw fact objects
facts = await ltm.retrieve_relevant("authentication", categories=["coding_style"], k=3)
```

#### Method Signatures

```python
class LongTermMemory:
    async def get_context_for_query(
        self,
        query: str,
        k: int = 5,
    ) -> str:
        """
        Get formatted memory context string to inject into agent prompt.
        Returns empty string if no relevant facts.
        """

    async def retrieve_relevant(
        self,
        query: str,
        k: int = 5,
        min_score: float = 0.3,
        categories: Optional[List[str]] = None,
    ) -> List[MemoryFact]:
        """
        Retrieve facts relevant to a query via semantic search.
        Filter by categories if provided.
        """

    async def extract_and_store_facts(
        self,
        thread_id: str,
        messages: List[BaseMessage],
        max_facts: int = 10,
    ) -> List[MemoryFact]:
        """
        Extract facts from a conversation and store them.
        Called after agent completes a turn (in orchestrator or via hook).
        """

    async def delete_facts_by_thread(self, thread_id: str) -> int:
        """Delete all facts originating from a specific thread."""
```

#### How It Works

```
Conversation Turn
      ↓
Agent responds (HITL may be involved)
      ↓
Background task: extract_and_store_facts(messages, thread_id)
      ↓
LLM analyzes conversation → outputs structured JSON facts
      ↓
Each fact embedded + stored in vector store (Qdrant/ChromaDB per config)
      ↓
Future queries: retrieve_relevant(query) → embed query → similarity search → return facts
```

#### Extraction Prompt (Full)

```python
EXTRACT_FACTS_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a memory extraction system. Analyze the conversation and extract
salient, durable facts that would be useful in FUTURE conversations.

Extract ONLY facts that are:
- Persistent across sessions (preferences, patterns, project context)
- Specific and actionable (not vague generalities)
- Not already obvious from the codebase itself

Categories:
- "preference": User's coding style, tool preferences, workflow choices
- "pattern": Recurring patterns in how they work or what they ask
- "fact": Concrete information about the project/team/environment
- "project_context": Architectural decisions, tech stack, conventions

Return JSON array of objects with fields:
  content, category, confidence (0.0-1.0), metadata (optional dict)

Examples:
[
  {"content": "User prefers pytest with fixtures over unittest", "category": "preference", "confidence": 0.9},
  {"content": "Project uses FastAPI with async SQLAlchemy", "category": "project_context", "confidence": 0.95},
  {"content": "User often asks for tests before implementation", "category": "pattern", "confidence": 0.7}
]

If no extractable facts, return empty array []."""),
    ("human", "Conversation:\n{conversation}\n\nExtract facts as JSON array:"),
])
```

#### Storage in Vector Database

```python
async def _store_facts(self, facts: List[MemoryFact]) -> None:
    """Store facts in vector store."""
    store = self._get_vector_store()

    texts = [json.dumps(fact.to_dict()) for fact in facts]
    metadatas = [
        {
            "fact_id": fact.id,
            "category": fact.category,
            "confidence": fact.confidence,
            "source_thread_id": fact.source_thread_id,
            "created_at": fact.created_at,
        }
        for fact in facts
    ]

    await store.aadd_texts(texts=texts, metadatas=metadatas)
```

**Vector Store Configuration** (uses same config as RAG):
```yaml
vector_store:
  provider: qdrant                        # qdrant | chromadb | elasticsearch
  retrieval_mode: hybrid
```

Collection name: `"user_memory"` (separate from codebase index)

---

## ⚙️ Configuration

Configured in `config.yaml`:

```yaml
memory:
  db_path: .memory/memory.db              # SQLite for short-term checkpointer
  summarize_at_tokens: 4000               # Trigger summarization
  keep_last_messages: 20                  # Verbatim retention

vector_store:
  provider: qdrant                        # qdrant | chromadb | elasticsearch
  retrieval_mode: hybrid
```

> **Note**: Long-term memory uses the same vector store as RAG (configured in `vector_store.provider`).

---

## 🔧 How It Works Together

### Complete Memory Flow

```
User Query
     ↓
handle_query() in orchestrator.py
     ↓
1. get_long_term_memory().get_context_for_query(question)
     ↓    (retrieves relevant facts, prepends to question)
Modified question with memory context
     ↓
2. agent.ainvoke() with thread_id (session ID)
     ↓
3. Short-term: checkpointer saves state to SQLite
     ↓
4. SummarizationMiddleware triggers if token threshold hit
     ↓
5. Response returned to user
     ↓
6. Background: extract_and_store_facts(messages, thread_id)
     ↓
    Facts embedded + stored in vector DB for future sessions
```

### Component Interaction Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ORCHESTRATOR                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  question = "How do I run tests?"                                          │
│        │                                                                    │
│        ▼                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ ltm.get_context_for_query(question)                                 │   │
│  │   → embeds query                                                    │   │
│  │   → searches "user_memory" collection                               │   │
│  │   → returns: "=== Relevant Long-Term Memory ===\n                   │   │
│  │       - [preference] User prefers pytest -x (conf: 0.90)"          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│        │                                                                    │
│        ▼                                                                    │
│  augmented_question = memory_context + "\n\nUser question: " + question   │
│        │                                                                    │
│        ▼                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ agent.ainvoke({messages: [augmented_question]}, config={thread_id}) │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│        │                                                                    │
│        ▼                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ LANGGRAPH AGENT EXECUTION                                           │   │
│  │  ├─ Short-term checkpointer (SQLite) saves each step               │   │
│  │  ├─ SummarizationMiddleware compresses if >4000 tokens             │   │
│  │  ├─ HITL middleware pauses for dangerous tools                     │   │
│  │  └─ Response generated                                              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│        │                                                                    │
│        ▼                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ finally: asyncio.create_task(ltm.extract_and_store_facts(...))     │   │
│  │   → formats conversation                                            │   │
│  │   → LLM extracts JSON facts                                         │   │
│  │   → embeds each fact                                                │   │
│  │   → stores in vector DB (collection="user_memory")                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📝 Usage Examples

### Session Management
```python
from educosys_claude.memory import get_current_session, new_session, switch_session

session_id = get_current_session()      # "a1b2c3d4-..."
new_id = new_session()                  # Creates new, persists to .memory/current_session
switch_session("existing-uuid")         # Switch to existing session
```

### Accessing Long-Term Memory
```python
from educosys_claude.memory import get_long_term_memory

ltm = get_long_term_memory()

# Get context for a question (auto-injected in orchestrator)
context = await ltm.get_context_for_query("How do I run tests?")
# Returns: "=== Relevant Long-Term Memory ===\n- [preference] User prefers pytest -x (conf: 0.90)\n"

# Manual fact extraction (e.g., after a design discussion)
await ltm.extract_and_store_facts(conversation_messages, "thread-456")

# Query specific categories
facts = await ltm.retrieve_relevant("auth", categories=["coding_style"], k=3)
# Returns: [MemoryFact(category="coding_style", content="Use JWT for auth...", conf=0.85), ...]
```

### Debugging / Inspecting Memory
```python
# Inspect all stored facts
facts = await ltm.retrieve_relevant("", k=50, min_score=0.0)
for f in facts:
    print(f"[{f.category}] {f.content[:80]} (conf: {f.confidence})")

# Check short-term SQLite
import sqlite3
conn = sqlite3.connect(".memory/memory.db")
cursor = conn.execute("SELECT * FROM checkpoints WHERE thread_id = ?", (session_id,))
for row in cursor:
    print(row)
```

---

## 🔄 Integration Points

| Component | Uses |
|-----------|------|
| `main.py` | `get_checkpointer_db_path()`, `get_current_session()` |
| `agent/factory.py` | Checkpointer passed to `build_agent()`; middleware stack |
| `agent/orchestrator.py` | `get_long_term_memory().get_context_for_query()`, background `extract_and_store_facts()` |
| `llm/factory.py` | `get_llm()` for summarization + fact extraction |

---

## 📊 Performance Characteristics

| Aspect | Short-Term | Long-Term |
|--------|------------|-----------|
| **Storage** | SQLite (`.memory/memory.db`) | Vector DB (Qdrant/Chroma) |
| **Latency** | Minimal (checkpoint write) | Extraction: ~1-2s LLM call; Retrieval: ~50-200ms |
| **Scope** | Single session | Cross-session, persistent |
| **Content** | Full conversation (summarized) | Distilled facts only |
| **Token Cost** | Summarization LLM calls | Extraction LLM calls + embeddings |
| **Capacity** | Unbounded (auto-summarizes) | Vector store size limit |

---

## 🛠️ Customization

### Adjust Summarization (config.yaml)
```yaml
memory:
  summarize_at_tokens: 6000      # Higher = less frequent summarization
  keep_last_messages: 15         # More verbatim context
```

### Long-Term Memory Categories
Modify the extraction prompt in `long_term.py` to add/change categories:
```python
# In EXTRACT_FACTS_PROMPT system message, add:
# - "user_preferences": Explicit user preferences
# - "deployment_config": CI/CD, infra details
# - "team_conventions": Code review standards, naming
```

### Vector Store for Long-Term
Uses same config as RAG (`vector_store.provider`). To use separate store, modify `_get_vector_store()` in `long_term.py`:
```python
def _get_vector_store(self):
    # Use different path/collection
    client = QdrantClient(path="/custom/path/qdrant_memory")
    # ...
```

---

## 💡 Best Practices

1. **Let background extraction run** — Don't await it in the response path
2. **Filter by category** — Improves relevance (e.g., only `coding_style` for style questions)
3. **Confidence threshold** — Ignore facts with `confidence < 0.6` for critical decisions
4. **Session hygiene** — `/new_session` starts fresh thread; old facts still retrievable
5. **Monitor vector store size** — Periodically clean stale facts in production
6. **Tune extraction prompt** — Add domain-specific examples for better fact quality

---

## 🔧 Troubleshooting

| Issue | Solution |
|-------|----------|
| No facts retrieved | Check vector store has data; verify embedding model matches |
| Facts seem stale | Add `updated_at` filtering; re-extract after major changes |
| High token usage from memory context | Reduce `k` in `get_context_for_query(k=3)` |
| Extraction fails silently | Check logs for LLM errors; verify JSON parsing in `_parse_llm_facts` |
| Short-term not summarizing | Verify `summarize_at_tokens` config; check middleware order |
| Session not persisting | Check `.memory/current_session` file permissions |
| 400 error on HITL resume | Ensure `PatchToolCallsMiddleware` is FIRST in middleware list |

---

## 📋 Logging Configuration

### Overview
Logging is configured in `config.yaml` under the `logging` key and initialized in `observability/logger.py`. It provides:
- **Console output** (configurable)
- **Rotating file output** (configurable path, max size, backup count)
- **Per-module DEBUG level** with third-party suppression at WARNING

### Config (`config.yaml`)
```yaml
logging:
  level: "DEBUG"                    # DEBUG | INFO | WARNING | ERROR
  file_path: ".radha/logs/agent.log"  # Log file path (rotated)
  max_bytes: 10485760               # 10 MB per file
  backup_count: 5                   # Keep 5 rotated files
  format: "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
  console: true                     # Also log to stdout
```

### Directory Structure
```
.radha/
└── logs/
    ├── agent.log           # Current log (max 10 MB)
    ├── agent.log.1         # Rotated backup
    ├── agent.log.2
    └── ...
```

### Usage in Code
```python
from educosys_claude.observability.logger import get_logger

logger = get_logger(__name__)
logger.debug("Detailed debug info")
logger.info("General information")
logger.warning("Something unexpected")
logger.error("Error occurred", exc_info=True)
```

### Output Example
```
2026-07-11 10:30:45,123 | DEBUG    | educosys_claude.memory.long_term | Extracted 3 facts from thread abc-123
2026-07-11 10:30:45,124 | INFO     | educosys_claude.agent.orchestrator | Handling query for session abc-123: How to run tests?
2026-07-11 10:30:45,156 | DEBUG    | educosys_claude.agent.orchestrator | Retrieved 2 long-term memory facts
2026-07-11 10:30:46,789 | WARNING  | educosys_claude.agent.factory | HITL interrupt for tool: run_command
```

### Third-Party Suppression
Noisy libraries set to WARNING automatically:
- `openai`, `httpx`, `httpcore`, `urllib3`
- `chromadb`, `qdrant_client`
- `langchain`, `langgraph`, `langchain_core`, `langchain_openai`

---

## 📚 Related Files

```
educosys_claude/
├── memory/
│   ├── __init__.py           # Exports all public APIs
│   ├── session.py            # Session ID persistence
│   ├── short_term.py         # SQLite checkpointer + summarization
│   └── long_term.py          # Vector-based fact memory
├── agent/
│   ├── factory.py            # Agent build with middleware stack
│   └── orchestrator.py       # Query handling + memory injection
├── observability/
│   └── logger.py             # Logging setup + get_logger()
├── config.yaml               # Memory, vector store, logging, middleware config
└── docs/
    ├── MEMORY_PACKAGE.md     # This file
    └── MIDDLEWARE_PACKAGE.md # Middleware stack documentation
```