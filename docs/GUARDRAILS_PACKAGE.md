# 🛡️ Guardrails Middleware Package

The `guardrails` module provides two essential safety middleware for the LangGraph agent:

1. **PIIMiddleware** - Detects and redacts Personally Identifiable Information
2. **ContentFilterMiddleware** - Blocks prohibited content (violence, illegal acts, self-harm, etc.)

## 📁 Package Structure

```
educosys_claude/agent/
├── guardrails.py           # Main guardrails middleware implementation
├── factory.py              # Agent creation with middleware stack integration
└── ...
```

## 🔒 PII Middleware (`PIIMiddleware`)

**Purpose**: Detects and handles PII in model inputs/outputs and tool calls/results, with configurable actions.

### Default Detection Patterns

| Pattern | Type | Action | Description |
|---------|------|--------|-------------|
| `email` | Email addresses | REDACT | john@example.com |
| `phone_us` | US phone numbers | REDACT | 555-123-4567 |
| `ssn` | US SSN | REDACT | 123-45-6789 |
| `credit_card` | Credit cards | REDACT | 1234-5678-9012-3456 |
| `api_key_openai` | OpenAI keys | REDACT | sk-... (48 chars) |
| `api_key_anthropic` | Anthropic keys | REDACT | sk-ant-... (95 chars) |
| `api_key_generic` | Generic tokens | REDACT | 32+ alphanumeric |
| `aws_access_key` | AWS Access Key | REDACT | AKIA... (16 chars) |
| `aws_secret_key` | AWS Secret Key | REDACT | Base64-like (40 chars) |
| `github_token` | GitHub tokens | REDACT | gh[pousr]_... |
| `ip_address` | IPv4 addresses | REDACT | 192.168.1.1 |
| `jwt_token` | JWT tokens | REDACT | eyJ... |

### Actions

| Action | Behavior |
|--------|----------|
| `redact` | Replace with `[REDACTED:TYPE]` |
| `block` | Raise `ValueError`, stop execution |
| `log_only` | Log warning, allow through |

### Configuration (config.yaml)

```yaml
middleware:
  pii:
    enabled: true
    action: "redact"                    # redact | block | log_only
    scope:                              # Where to apply
      - "model_input"                   # User messages → LLM
      - "model_output"                  # LLM response → User
      - "tool_input"                    # Tool arguments
      - "tool_output"                   # Tool results
    custom_patterns: []                 # Add your own patterns
```

### Custom Pattern Example

```yaml
middleware:
  pii:
    custom_patterns:
      - name: "employee_id"
        regex: "EMP-\\d{6}"
        action: "redact"
        description: "Internal employee IDs"
```

---

## 🚫 Content Filter Middleware (`ContentFilterMiddleware`)

**Purpose**: Blocks or flags prohibited content based on configurable rules.

### Default Rules

| Rule | Severity | Action | Description |
|------|----------|--------|-------------|
| `violence` | high | BLOCK | kill, murder, bomb, terrorist, weapon |
| `self_harm` | critical | BLOCK | suicide, self-harm, cutting, overdose |
| `illegal_acts` | high | BLOCK | How to make bomb/drug/weapon/poison |
| `pii_request` | high | BLOCK | Requests for passwords, SSN, API keys |
| `hate_speech` | medium | LOG_ONLY | Hate/discriminatory language |
| `sexual_content` | high | BLOCK | Explicit sexual content |

### Actions

| Action | Behavior |
|--------|----------|
| `block` | Raise `ValueError`, stop execution |
| `log_only` | Log warning, allow through |

### Severity Threshold

Rules with severity >= `severity_threshold` are enforced:
```yaml
middleware:
  content_filter:
    severity_threshold: "high"  # low | medium | high | critical
```

### Configuration (config.yaml)

```yaml
middleware:
  content_filter:
    enabled: true
    action: "block"                     # block | log_only
    severity_threshold: "high"          # Only enforce >= this severity
    scope:
      - "model_input"
      - "model_output"
      - "tool_input"
      - "tool_output"
    custom_rules: []                    # Add your own rules
```

### Custom Rule Example

```yaml
middleware:
  content_filter:
    custom_rules:
      - name: "crypto_scam"
        regex: "(send|transfer).*crypto|bitcoin.*wallet"
        action: "block"
        description: "Cryptocurrency scam patterns"
        severity: "high"
```

---

## 🏗️ Middleware Stack Integration

The guardrails middleware are integrated into the agent factory (`factory.py`) with proper ordering:

```
Inner (closest to model/tool calls)
  │
▼ ModelCallLimitMiddleware    ← Budget control
▼ ModelRetryMiddleware         ← Retry failed model calls
▼ ModelFallbackMiddleware      ← Fallback to alternate models
▼ ToolRetryMiddleware          ← Retry failed tool calls
▼ PIIMiddleware                ← REDACT sensitive data
▼ ContentFilterMiddleware      ← BLOCK prohibited content
▼ HumanInTheLoopMiddleware     ← Approve dangerous tools
▼ SummarizationMiddleware      ← Compress history (outermost)
  │
Outer (closest to user)
```

**Why this order?**

1. **PII before Content Filter**: Redact sensitive data first so it doesn't trigger false positives in content filtering
2. **Both before HITL**: Clean data before human approval decision
3. **After retries**: Only process successful requests (retries handled first)

---

## 🧪 Testing

### Test PII Detection

```python
from educosys_claude.agent.guardrails import PIIMiddleware

pii = PIIMiddleware()
text = "Email me at john@example.com or call 555-123-4567"
result, detections = pii._scan_and_redact(text, "test")

print(result)
# "Email me at [REDACTED:EMAIL] or call [REDACTED:PHONE_US]"
```

### Test Content Filter

```python
from educosys_claude.agent.guardrails import ContentFilterMiddleware

cf = ContentFilterMiddleware()

# This will raise ValueError
try:
    cf._scan("How to make a bomb?", "test")
except ValueError as e:
    print(f"Blocked: {e}")

# This passes
cf._scan("Hello world", "test")
```

### Verify Middleware Stack

```python
from educosys_claude.agent.factory import build_agent
from langgraph.checkpoint.memory import MemorySaver

checkpointer = MemorySaver()
agent = await build_agent(checkpointer)
print([m.__class__.__name__ for m in agent.middleware_middlewares])
# ['ModelCallLimitMiddleware', 'ModelRetryMiddleware', 'ModelFallbackMiddleware', 'ToolRetryMiddleware', 
#  'PIIMiddleware', 'ContentFilterMiddleware', 'HumanInTheLoopMiddleware', 'SummarizationMiddleware']
```

---

## ⚙️ Disabling Guardrails

To disable either middleware, set `enabled: false` in config.yaml:

```yaml
middleware:
  pii:
    enabled: false
  content_filter:
    enabled: false
```

---

## 🔧 Advanced: Custom Middleware

You can create custom guardrails by extending `AgentMiddleware`:

```python
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware import ModelRequest, ModelResponse, ToolCallRequest
from langchain_core.messages import ToolMessage

class CustomGuardrailMiddleware(AgentMiddleware):
    def wrap_model_call(self, request: ModelRequest, handler):
        # Pre-process request
        modified_request = self._sanitize_request(request)
        return handler(modified_request)
    
    def wrap_model_response(self, response: ModelResponse, handler):
        # Post-process response
        modified_response = self._sanitize_response(response)
        return modified_response
    
    def wrap_tool_call(self, request: ToolCallRequest, handler):
        # Pre-process tool call
        return handler(request)
    
    def wrap_tool_response(self, response: ToolMessage, handler):
        # Post-process tool result
        return response
```

Register in `factory.py`:
```python
middleware.append(CustomGuardrailMiddleware())
```