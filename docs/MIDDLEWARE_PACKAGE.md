# ⚙️ Middleware Package

The middleware package provides cross-cutting concerns for agent execution: fault tolerance, rate limiting, fallbacks, and human-in-the-loop approval.

## 📁 Package Structure

```
educosys_claude/agent/
├── factory.py              # Agent creation with middleware stack
├── orchestrator.py         # Query handling + memory injection
└── middleware.py           # Custom middleware (if needed)
```

---

## 🧩 Middleware Stack

The agent is built with a middleware stack in `agent/factory.py`. Order matters — the first middleware wraps the innermost (model/tool calls), the last wraps the outermost.

```
Execution Flow (normal):
─────────────────────────────────────────────────────────────────────
User Query
    ↓
ModelCallLimitMiddleware          ← Counts model calls per thread/run
    ↓
ModelRetryMiddleware              ← Retries failed model calls (exponential backoff)
    ↓
ModelFallbackMiddleware           ← Falls back to alt models if primary down
    ↓
ToolRetryMiddleware               ← Retries failed tool calls (scoped to tools)
    ↓
HumanInTheLoopMiddleware          ← Pauses for approval on dangerous tools
    ↓
SummarizationMiddleware           ← Compresses history if tokens exceed threshold
    ↓
Agent Core (LLM + Tools)
─────────────────────────────────────────────────────────────────────

On HITL Resume:
HumanInTheLoopMiddleware runs FIRST to process decisions, then SummarizationMiddleware
```

---

## 1. ModelCallLimitMiddleware

**Purpose**: Prevents runaway model calls that could exhaust budget or hit rate limits.

**Config** (`config.yaml`):
```yaml
middleware:
  model_call_limit:
    enabled: true
    thread_limit: 100      # Max model calls per thread (conversation)
    run_limit: 50          # Max model calls per single run
    exit_behavior: "end"   # "end" = return early gracefully; "error" = raise exception
```

**Behavior**:
- Tracks calls per `thread_id` (conversation) and per run (single `ainvoke()`)
- When limit reached: stops execution per `exit_behavior`
- Useful for cost control and preventing infinite loops

---

## 2. ModelRetryMiddleware

**Purpose**: Automatically retries failed model API calls with exponential backoff.

**Config** (`config.yaml`):
```yaml
middleware:
  model_retry:
    enabled: true
    max_retries: 3                  # Total attempts = max_retries + 1
    backoff_factor: 2.0             # Exponential multiplier
    initial_delay: 1.0              # Seconds before first retry
    max_delay: 60.0                 # Cap on delay
    jitter: true                    # ±25% random jitter
    retry_on: []                    # Empty = all exceptions; or list: ["TimeoutError", "ConnectionError"]
    on_failure: "continue"          # "continue" | "error" | custom_formatter
```

**Behavior**:
- Retries on network errors, rate limits (429), server errors (5xx)
- Does NOT retry on client errors (401, 404, 400)
- On exhausted retries:
  - `"continue"`: Returns `AIMessage` with error, lets agent try to recover
  - `"error"`: Re-raises exception, stops agent
  - Custom callable: Formats error message for `AIMessage`

**Example retried exceptions**: `TimeoutError`, `ConnectionError`, `httpx.TimeoutException`, `openai.RateLimitError`

---

## 3. ModelFallbackMiddleware

**Purpose**: Switches to alternative model(s) if primary model is unavailable.

**Config** (`config.yaml`):
```yaml
middleware:
  model_fallback:
    enabled: true
    fallback_models: ["gpt-4o-mini", "gpt-3.5-turbo"]  # Model identifiers for init_chat_model
```

**Behavior**:
- Tries primary model first
- On failure, tries fallbacks in order
- Falls back only if primary model call fails completely (not on retries — those are handled by ModelRetryMiddleware)
- Loaded via `langchain.chat_models.init_chat_model()`

**Example**: Primary = `gpt-4o`, fallback = `gpt-4o-mini` → if GPT-4o is down, uses GPT-4o-mini automatically

---

## 4. ToolRetryMiddleware

**Purpose**: Retries failed tool calls (scoped to specific tools that benefit from retries).

**Config** (`config.yaml`):
```yaml
middleware:
  tool_retry:
    enabled: true
    max_retries: 2
    backoff_factor: 2.0
    initial_delay: 1.0
    max_delay: 30.0
    jitter: true
    tools: []                    # Empty = all tools; or ["search_codebase", "run_command"]
    retry_on: []                 # Empty = all exceptions; or ["TimeoutError", "ConnectionError"]
    on_failure: "continue"       # "continue" | "error" | custom_formatter
```

**Behavior**:
- Only retries specified tools (or all if empty)
- Does NOT retry local filesystem ops (read_file, write_file) — they fail fast
- DOES retry external API tools: `search_codebase`, `run_command`, MCP tools, web search
- On exhausted retries: returns error message to model for recovery

**Recommended tools to retry**:
- `search_codebase` (vector DB queries)
- `run_command`, `run_in_directory` (external processes)
- MCP tools (GitHub API, etc.)

**Tools NOT to retry**: `read_file`, `write_file`, `list_directory`, `file_exists` (local FS ops)

---

## 5. HumanInTheLoopMiddleware

**Purpose**: Pauses agent execution for human approval before executing dangerous tools.

**Config** (code in `factory.py`):
```python
interrupt_on = {
    "run_command": {"allowed_decisions": ["approve", "edit", "reject"]},
    "run_in_directory": {"allowed_decisions": ["approve", "edit", "reject"]},
    "write_file": {"allowed_decisions": ["approve", "edit", "reject"]},
    "append_file": {"allowed_decisions": ["approve", "edit", "reject"]},
    # Plus all GitHub MCP tools...
}
```

**Behavior**:
- Intercepts tool calls matching `interrupt_on` keys
- Pauses graph execution via LangGraph `interrupt()`
- Local: Prompts via `rich.Prompt` in terminal
- GitHub Actions: Posts comment to issue/gist, polls for `/APPROVE`, `/REJECT`, `/EDIT` commands
- On resume: Executes approved/edited calls, returns rejection messages for rejected calls

**Decisions**:
| Decision | Behavior |
|----------|----------|
| `approve` | Execute tool with original args |
| `edit` | Execute tool with modified args |
| `reject` | Return error message to model |
| `respond` | Return human message as tool result |

---

## 6. SummarizationMiddleware (Short-Term Memory)

**Purpose**: Compresses conversation history when token count exceeds threshold.

**Config** (`config.yaml`):
```yaml
memory:
  summarize_at_tokens: 4000      # Trigger threshold
  keep_last_messages: 20         # Keep N most recent messages verbatim
```

**Behavior**:
- Runs after each graph step
- If tokens > threshold: summarizes oldest messages (excluding last N)
- Replaces with `SystemMessage(summary)` + recent messages
- Checkpointer saves compressed state to SQLite

---

## 🔧 Adding Custom Middleware

Create a custom middleware class:

```python
# educosys_claude/agent/custom_middleware.py
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.model_retry import ModelRequest, ModelResponse
from typing import Callable

class LoggingMiddleware(AgentMiddleware):
    """Log all model requests/responses."""

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        logger.info(f"Model call: {request.messages[-1].content[:100]}...")
        response = handler(request)
        logger.info(f"Model response: {response.content[:100]}...")
        return response
```

Add to stack in `factory.py`:
```python
from educosys_claude.agent.custom_middleware import LoggingMiddleware

middleware = [
    LoggingMiddleware(),
    # ... other middleware
]
```

---

## 📊 Middleware Configuration Reference

| Middleware | Config Key | Required | Default |
|------------|------------|----------|---------|
| ModelCallLimit | `middleware.model_call_limit` | No | enabled, thread=100, run=50 |
| ModelRetry | `middleware.model_retry` | No | enabled, retries=3, backoff=2.0 |
| ModelFallback | `middleware.model_fallback` | No | enabled, no fallbacks |
| ToolRetry | `middleware.tool_retry` | No | enabled, retries=2, all tools |
| HITL | `factory.py` code | Yes | — |
| Summarization | `memory.*` | No | tokens=4000, keep=20 |

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| Model calls exceed limit unexpectedly | Check `thread_limit` vs `run_limit`; long conversations accumulate |
| Retries not working | Verify exception types in `retry_on`; check model's native `max_retries` |
| Fallback not triggering | Ensure fallback models load correctly (check logs); primary must fail completely |
| Tool retries on local FS ops | Add tool names to `tools` list explicitly; or set `tools: []` for none |
| HITL not pausing | Verify tool name matches exactly; check `interrupt_on` dict keys |
| Summarization breaking HITL | Ensure `PatchToolCallsMiddleware` (or equivalent) runs before Summarization on resume |
| 400 error: tool_calls without tool_messages | Middleware order: HITL repair MUST be before Summarization on resume |

---

## 📝 Best Practices

1. **Scope tool retries** — Only retry external API tools, not local FS ops
2. **Set call limits** — Prevent runaway costs with `ModelCallLimitMiddleware`
3. **Configure fallbacks** — Always have at least one fallback model for production
4. **Tune retry delays** — Start with `initial_delay=1.0`, `backoff_factor=2.0`, `max_delay=60.0`
5. **Monitor logs** — Check middleware logs for retry/fallback activity
6. **Test HITL flows** — Verify approve/edit/reject work in both local and CI environments