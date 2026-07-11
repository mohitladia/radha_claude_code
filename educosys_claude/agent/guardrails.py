"""
Guardrails Middleware for LangGraph Agent.

Provides PII detection/redaction and content filtering middleware that integrates
with LangChain's AgentMiddleware system.
"""

import re
from typing import Any, Optional, List, Dict, Union
from dataclasses import dataclass
from enum import Enum

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse, ToolCallRequest
from langchain_core.messages import BaseMessage, AIMessage, ToolMessage
from langgraph.types import Command

from educosys_claude.config import config
from educosys_claude.observability.logger import get_logger

logger = get_logger(__name__)


class PIIAction(str, Enum):
    """Action to take when PII is detected."""
    REDACT = "redact"      # Replace with [REDACTED]
    BLOCK = "block"        # Raise exception / block request
    LOG_ONLY = "log_only"  # Log warning but allow through


class ContentFilterAction(str, Enum):
    """Action to take when prohibited content is detected."""
    BLOCK = "block"        # Raise exception / block request
    LOG_ONLY = "log_only"  # Log warning but allow through


@dataclass
class PIIPattern:
    """PII detection pattern with metadata."""
    name: str
    pattern: re.Pattern
    action: PIIAction = PIIAction.REDACT
    description: str = ""


@dataclass
class ContentFilterRule:
    """Content filtering rule."""
    name: str
    pattern: re.Pattern
    action: ContentFilterAction = ContentFilterAction.BLOCK
    description: str = ""
    severity: str = "high"  # low, medium, high, critical


# Built-in PII patterns
DEFAULT_PII_PATTERNS = [
    PIIPattern(
        name="email",
        pattern=re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
        action=PIIAction.REDACT,
        description="Email addresses",
    ),
    PIIPattern(
        name="phone_us",
        pattern=re.compile(r"\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b"),
        action=PIIAction.REDACT,
        description="US phone numbers",
    ),
    PIIPattern(
        name="ssn",
        pattern=re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        action=PIIAction.REDACT,
        description="US Social Security Numbers",
    ),
    PIIPattern(
        name="credit_card",
        pattern=re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
        action=PIIAction.REDACT,
        description="Credit card numbers (basic)",
    ),
    PIIPattern(
        name="api_key_openai",
        pattern=re.compile(r"\bsk-[A-Za-z0-9]{48}\b"),
        action=PIIAction.REDACT,
        description="OpenAI API keys",
    ),
    PIIPattern(
        name="api_key_anthropic",
        pattern=re.compile(r"\bsk-ant-[A-Za-z0-9_-]{95}\b"),
        action=PIIAction.REDACT,
        description="Anthropic API keys",
    ),
    PIIPattern(
        name="api_key_generic",
        pattern=re.compile(r"\b[A-Za-z0-9]{32,}\b"),
        action=PIIAction.REDACT,
        description="Generic long API keys/tokens",
    ),
    PIIPattern(
        name="aws_access_key",
        pattern=re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        action=PIIAction.REDACT,
        description="AWS Access Key IDs",
    ),
    PIIPattern(
        name="aws_secret_key",
        pattern=re.compile(r"\b[0-9a-zA-Z/+]{40}\b"),
        action=PIIAction.REDACT,
        description="AWS Secret Access Keys",
    ),
    PIIPattern(
        name="github_token",
        pattern=re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{36,}\b"),
        action=PIIAction.REDACT,
        description="GitHub tokens (pat, oauth, user, server, refresh)",
    ),
    PIIPattern(
        name="ip_address",
        pattern=re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"),
        action=PIIAction.REDACT,
        description="IPv4 addresses",
    ),
    PIIPattern(
        name="jwt_token",
        pattern=re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
        action=PIIAction.REDACT,
        description="JWT tokens",
    ),
]

# Built-in content filter rules
DEFAULT_CONTENT_FILTER_RULES = [
    ContentFilterRule(
        name="violence",
        pattern=re.compile(r"\b(kill|murder|assassinate|bomb|terrorist|weapon)\b", re.IGNORECASE),
        action=ContentFilterAction.BLOCK,
        description="Violence-related content",
        severity="high",
    ),
    ContentFilterRule(
        name="self_harm",
        pattern=re.compile(r"\b(suicide|self.harm|cutting|overdose)\b", re.IGNORECASE),
        action=ContentFilterAction.BLOCK,
        description="Self-harm content",
        severity="critical",
    ),
    ContentFilterRule(
        name="illegal_acts",
        pattern=re.compile(r"\b(how to (?:make|create|build) (?:bomb|drug|weapon|poison)|illegal (?:activity|act|drug))\b", re.IGNORECASE),
        action=ContentFilterAction.BLOCK,
        description="Instructions for illegal activities",
        severity="high",
    ),
    ContentFilterRule(
        name="pii_request",
        pattern=re.compile(r"\b(give me|show me|what is) (?:your|their|the) (?:password|ssn|social security|credit card|api key|secret)\b", re.IGNORECASE),
        action=ContentFilterAction.BLOCK,
        description="Requests for sensitive information",
        severity="high",
    ),
    ContentFilterRule(
        name="hate_speech",
        pattern=re.compile(r"\b(hate|discriminat|supremacist)\b", re.IGNORECASE),
        action=ContentFilterAction.LOG_ONLY,
        description="Potential hate speech",
        severity="medium",
    ),
    ContentFilterRule(
        name="sexual_content",
        pattern=re.compile(r"\b(explicit sexual|pornograph|sexually explicit)\b", re.IGNORECASE),
        action=ContentFilterAction.BLOCK,
        description="Sexual content",
        severity="high",
    ),
]


def _scan_text_for_pii(text: str, patterns: List[PIIPattern], context: str) -> tuple[str, List[Dict]]:
    """Scan text for PII using provided patterns. Returns (processed_text, detections)."""
    if not isinstance(text, str):
        return text, []

    detections = []
    result = text

    for pattern in patterns:
        matches = list(pattern.pattern.finditer(text))
        if not matches:
            continue

        for match in matches:
            detection = {
                "type": pattern.name,
                "match": match.group(),
                "position": match.span(),
                "action": pattern.action.value,
                "description": pattern.description,
            }
            detections.append(detection)

            if pattern.action == PIIAction.REDACT:
                placeholder = f"[REDACTED:{pattern.name.upper()}]"
                result = result[:match.start()] + placeholder + result[match.end():]
            elif pattern.action == PIIAction.BLOCK:
                raise ValueError(f"PII blocked: {pattern.name} detected in {context}")
            elif pattern.action == PIIAction.LOG_ONLY:
                logger.warning(f"PII detected in {context}: {pattern.name} at {match.span()}")

    if detections:
        logger.info(f"PII scan ({context}): {len(detections)} detection(s) - {[d['type'] for d in detections]}")

    return result, detections


def _scan_text_for_content(text: str, rules: List[ContentFilterRule], context: str) -> List[Dict]:
    """Scan text for prohibited content. Returns violations list."""
    if not isinstance(text, str):
        return []

    violations = []

    for rule in rules:
        matches = list(rule.pattern.finditer(text))
        if not matches:
            continue

        for match in matches:
            violation = {
                "rule": rule.name,
                "match": match.group(),
                "position": match.span(),
                "action": rule.action.value,
                "description": rule.description,
                "severity": rule.severity,
            }
            violations.append(violation)

            if rule.action == ContentFilterAction.BLOCK:
                logger.error(f"Content blocked ({context}): {rule.name} - {rule.description}")
                raise ValueError(f"Content blocked: {rule.name} detected in {context}")
            elif rule.action == ContentFilterAction.LOG_ONLY:
                logger.warning(f"Content flagged ({context}): {rule.name} at {match.span()}")

    if violations:
        logger.info(f"Content filter scan ({context}): {len(violations)} violation(s) - {[v['rule'] for v in violations]}")

    return violations


def _process_message_content(content: Any, patterns: List[PIIPattern], rules: List[ContentFilterRule], context: str, apply_pii: bool, apply_content: bool) -> tuple[Any, List[Dict], List[Dict]]:
    """Process message content (string or list of content blocks) for PII and content filtering."""
    all_pii = []
    all_content = []

    if isinstance(content, str):
        if apply_pii:
            content, pii = _scan_text_for_pii(content, patterns, context)
            all_pii.extend(pii)
        if apply_content:
            content_violations = _scan_text_for_content(content, rules, context)
            all_content.extend(content_violations)
    elif isinstance(content, list):
        # Handle multimodal content (list of dicts with text/image)
        processed = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text", "")
                if apply_pii:
                    text, pii = _scan_text_for_pii(text, patterns, context)
                    all_pii.extend(pii)
                if apply_content:
                    content_violations = _scan_text_for_content(text, rules, context)
                    all_content.extend(content_violations)
                processed.append({**block, "text": text})
            else:
                processed.append(block)
        content = processed

    return content, all_pii, all_content


class PIIMiddleware(AgentMiddleware):
    """
    Middleware to detect and redact PII in model requests/responses and tool calls/results.

    Operates on:
    - Model input (user messages before sending to LLM)
    - Model output (LLM responses before returning to user)
    - Tool input (arguments passed to tools)
    - Tool output (results returned from tools)

    Configuration via config.yaml:
    ```yaml
    middleware:
      pii:
        enabled: true
        action: "redact"           # redact | block | log_only
        scope: ["model_input", "model_output", "tool_input", "tool_output"]
        custom_patterns: []        # List of {name, regex, action, description}
    ```
    """

    def __init__(
        self,
        patterns: Optional[List[PIIPattern]] = None,
        action: PIIAction = PIIAction.REDACT,
        scope: Optional[List[str]] = None,
        custom_patterns: Optional[List[Dict]] = None,
    ):
        """
        Initialize PII Middleware.

        Args:
            patterns: List of PIIPattern objects (uses DEFAULT_PII_PATTERNS if None)
            action: Default action for detected PII (overridden by per-pattern action)
            scope: Where to apply - ["model_input", "model_output", "tool_input", "tool_output"]
            custom_patterns: List of dicts with name, regex, action, description
        """
        super().__init__()
        self.patterns = patterns or DEFAULT_PII_PATTERNS
        self.default_action = action
        self.scope = scope or ["model_input", "model_output", "tool_input", "tool_output"]

        # Add custom patterns
        if custom_patterns:
            for cp in custom_patterns:
                try:
                    compiled = re.compile(cp["regex"])
                    pat_action = PIIAction(cp.get("action", "redact"))
                    self.patterns.append(PIIPattern(
                        name=cp["name"],
                        pattern=compiled,
                        action=pat_action,
                        description=cp.get("description", ""),
                    ))
                except Exception as e:
                    logger.warning(f"Failed to compile custom PII pattern {cp.get('name')}: {e}")

        logger.info(f"PIIMiddleware initialized: {len(self.patterns)} patterns, scope={self.scope}, default_action={action.value}")

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler,
    ) -> Union[ModelResponse, AIMessage]:
        """Process model input for PII before calling the LLM."""
        # Create a copy of messages to process
        if "model_input" in self.scope and request.messages:
            processed_messages = []
            for msg in request.messages:
                if hasattr(msg, "content") and msg.content:
                    content, _, _ = _process_message_content(
                        msg.content, self.patterns, [], "model_input", True, False
                    )
                    # Create new message with redacted content, preserving all attributes
                    kwargs = getattr(msg, "additional_kwargs", {}).copy()
                    # Preserve tool_calls if present (critical for tool calling chain)
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        kwargs["tool_calls"] = msg.tool_calls
                    # Preserve tool_call_id if present (required for ToolMessage constructor)
                    if hasattr(msg, "tool_call_id") and msg.tool_call_id:
                        kwargs["tool_call_id"] = msg.tool_call_id
                    # Preserve name if present
                    if hasattr(msg, "name") and msg.name:
                        kwargs["name"] = msg.name
                    new_msg = type(msg)(content=content, **kwargs)
                    processed_messages.append(new_msg)
                else:
                    processed_messages.append(msg)

            # Update request with processed messages
            request = ModelRequest(
                model=request.model,
                messages=processed_messages,
                system_message=request.system_message,
                tool_choice=request.tool_choice,
                tools=request.tools,
                response_format=request.response_format,
                state=request.state,
                runtime=request.runtime,
            )

        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler,
    ) -> Union[ModelResponse, AIMessage]:
        """Async: Process model input for PII before calling the LLM."""
        return self.wrap_model_call(request, handler)

    def wrap_model_response(
        self,
        response: ModelResponse,
        handler,
    ) -> Union[ModelResponse, AIMessage]:
        """Process model output for PII before returning."""
        if "model_output" in self.scope and response.result:
            processed_messages = []
            for msg in response.result:
                if hasattr(msg, "content") and msg.content:
                    content, _, _ = _process_message_content(
                        msg.content, self.patterns, [], "model_output", True, False
                    )
                    kwargs = getattr(msg, "additional_kwargs", {}).copy()
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        kwargs["tool_calls"] = msg.tool_calls
                    if hasattr(msg, "tool_call_id") and msg.tool_call_id:
                        kwargs["tool_call_id"] = msg.tool_call_id
                    if hasattr(msg, "name") and msg.name:
                        kwargs["name"] = msg.name
                    new_msg = type(msg)(content=content, **kwargs)
                    processed_messages.append(new_msg)
                else:
                    processed_messages.append(msg)

            response = ModelResponse(result=processed_messages)

        return response

    async def awrap_model_response(
        self,
        response: ModelResponse,
        handler,
    ) -> Union[ModelResponse, AIMessage]:
        """Async: Process model output for PII before returning."""
        return self.wrap_model_response(response, handler)

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler,
    ) -> Union[ToolMessage, Command]:
        """Process tool arguments for PII before executing tool."""
        if "tool_input" in self.scope and request.tool_call:
            args = request.tool_call.get("args", {})
            if isinstance(args, dict):
                processed_args = {}
                for key, value in args.items():
                    if isinstance(value, str):
                        content, _, _ = _process_message_content(
                            value, self.patterns, [], f"tool_input:{key}", True, False
                        )
                        processed_args[key] = content
                    else:
                        processed_args[key] = value
                if processed_args != args:
                    request = ToolCallRequest(
                        tool_call={**request.tool_call, "args": processed_args},
                        tool=request.tool,
                        state=request.state,
                        runtime=request.runtime,
                    )

        return handler(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler,
    ) -> Union[ToolMessage, Command]:
        """Async: Process tool arguments for PII before executing tool."""
        return self.wrap_tool_call(request, handler)

    def wrap_tool_response(
        self,
        response: ToolMessage,
        handler,
    ) -> ToolMessage:
        """Process tool output for PII before returning to agent."""
        if "tool_output" in self.scope and response.content:
            if isinstance(response.content, str):
                content, _, _ = _process_message_content(
                    response.content, self.patterns, [], f"tool_output:{response.name}", True, False
                )
                if content != response.content:
                    response = ToolMessage(
                        content=content,
                        tool_call_id=response.tool_call_id,
                        name=response.name,
                        status=response.status,
                    )

        return response

    async def awrap_tool_response(
        self,
        response: ToolMessage,
        handler,
    ) -> ToolMessage:
        """Async: Process tool output for PII before returning to agent."""
        return self.wrap_tool_response(response, handler)


class ContentFilterMiddleware(AgentMiddleware):
    """
    Middleware to detect and block prohibited content.

    Scans for: violence, self-harm, illegal acts, PII requests, hate speech, sexual content.

    Configuration via config.yaml:
    ```yaml
    middleware:
      content_filter:
        enabled: true
        action: "block"              # block | log_only
        scope: ["model_input", "model_output", "tool_input", "tool_output"]
        custom_rules: []             # List of {name, regex, action, description, severity}
    ```
    """

    def __init__(
        self,
        rules: Optional[List[ContentFilterRule]] = None,
        action: ContentFilterAction = ContentFilterAction.BLOCK,
        scope: Optional[List[str]] = None,
        custom_rules: Optional[List[Dict]] = None,
    ):
        """
        Initialize Content Filter Middleware.

        Args:
            rules: List of ContentFilterRule objects (uses DEFAULT_CONTENT_FILTER_RULES if None)
            action: Default action for detected content
            scope: Where to apply - ["model_input", "model_output", "tool_input", "tool_output"]
            custom_rules: List of dicts with name, regex, action, description, severity
        """
        super().__init__()
        self.rules = rules or DEFAULT_CONTENT_FILTER_RULES
        self.default_action = action
        self.scope = scope or ["model_input", "model_output", "tool_input", "tool_output"]

        # Add custom rules
        if custom_rules:
            for cr in custom_rules:
                try:
                    compiled = re.compile(cr["regex"])
                    rule_action = ContentFilterAction(cr.get("action", "block"))
                    self.rules.append(ContentFilterRule(
                        name=cr["name"],
                        pattern=compiled,
                        action=rule_action,
                        description=cr.get("description", ""),
                        severity=cr.get("severity", "high"),
                    ))
                except Exception as e:
                    logger.warning(f"Failed to compile custom content filter rule {cr.get('name')}: {e}")

        logger.info(f"ContentFilterMiddleware initialized: {len(self.rules)} rules, scope={self.scope}, default_action={action.value}")

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler,
    ) -> Union[ModelResponse, AIMessage]:
        """Scan model input for prohibited content."""
        if "model_input" in self.scope and request.messages:
            for msg in request.messages:
                if hasattr(msg, "content") and msg.content:
                    _process_message_content(
                        msg.content, [], self.rules, "model_input", False, True
                    )

        return handler(request)

    def wrap_model_response(
        self,
        response: ModelResponse,
        handler,
    ) -> Union[ModelResponse, AIMessage]:
        """Scan model output for prohibited content."""
        if "model_output" in self.scope and response.result:
            for msg in response.result:
                if hasattr(msg, "content") and msg.content:
                    _process_message_content(
                        msg.content, [], self.rules, "model_output", False, True
                    )

        return response

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler,
    ) -> Union[ToolMessage, Command]:
        """Scan tool arguments for prohibited content."""
        if "tool_input" in self.scope and request.tool_call:
            args = request.tool_call.get("args", {})
            if isinstance(args, dict):
                for key, value in args.items():
                    if isinstance(value, str):
                        _process_message_content(
                            value, [], self.rules, f"tool_input:{key}", False, True
                        )

        return handler(request)

    def wrap_tool_response(
        self,
        response: ToolMessage,
        handler,
    ) -> ToolMessage:
        """Scan tool output for prohibited content."""
        if "tool_output" in self.scope and response.content:
            if isinstance(response.content, str):
                _process_message_content(
                    response.content, [], self.rules, f"tool_output:{response.name}", False, True
                )

        return response

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler,
    ) -> Union[ModelResponse, AIMessage]:
        """Async: Scan model input for prohibited content."""
        return self.wrap_model_call(request, handler)

    async def awrap_model_response(
        self,
        response: ModelResponse,
        handler,
    ) -> Union[ModelResponse, AIMessage]:
        """Async: Scan model output for prohibited content."""
        return self.wrap_model_response(response, handler)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler,
    ) -> Union[ToolMessage, Command]:
        """Async: Scan tool arguments for prohibited content."""
        return self.wrap_tool_call(request, handler)

    async def awrap_tool_response(
        self,
        response: ToolMessage,
        handler,
    ) -> ToolMessage:
        """Async: Scan tool output for prohibited content."""
        return self.wrap_tool_response(response, handler)


def create_pii_middleware_from_config() -> Optional[PIIMiddleware]:
    """
    Create PIIMiddleware instance from config.yaml.

    Returns None if disabled.
    """
    mw_cfg = config.get("middleware", {}).get("pii", {})
    if not mw_cfg.get("enabled", True):
        logger.info("PIIMiddleware disabled via config")
        return None

    action = PIIAction(mw_cfg.get("action", "redact"))
    scope = mw_cfg.get("scope", ["model_input", "model_output", "tool_input", "tool_output"])
    custom_patterns = mw_cfg.get("custom_patterns", [])

    return PIIMiddleware(
        action=action,
        scope=scope,
        custom_patterns=custom_patterns,
    )


def create_content_filter_middleware_from_config() -> Optional[ContentFilterMiddleware]:
    """
    Create ContentFilterMiddleware instance from config.yaml.

    Returns None if disabled.
    """
    mw_cfg = config.get("middleware", {}).get("content_filter", {})
    if not mw_cfg.get("enabled", True):
        logger.info("ContentFilterMiddleware disabled via config")
        return None

    action = ContentFilterAction(mw_cfg.get("action", "block"))
    scope = mw_cfg.get("scope", ["model_input", "model_output", "tool_input", "tool_output"])
    custom_rules = mw_cfg.get("custom_rules", [])

    return ContentFilterMiddleware(
        action=action,
        scope=scope,
        custom_rules=custom_rules,
    )


# Exports
__all__ = [
    "PIIMiddleware",
    "ContentFilterMiddleware",
    "PIIPattern",
    "ContentFilterRule",
    "PIIAction",
    "ContentFilterAction",
    "DEFAULT_PII_PATTERNS",
    "DEFAULT_CONTENT_FILTER_RULES",
    "create_pii_middleware_from_config",
    "create_content_filter_middleware_from_config",
]