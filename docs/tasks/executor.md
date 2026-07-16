# Executor Module

## Purpose

Execute a **single task** via a fresh LangGraph agent, then evaluate output with **LLM-as-judge**.

## API

```python
from educosys_claude.tasks.executor import run_subtask_agent

output = await run_subtask_agent(
    task: dict,           # row from tasks table
    dep_outputs: list[dict]  # [{"id", "title", "result"}, ...]
) -> str                  # agent's summary (judge must pass)
```

---

## Per-Task Agent Construction

### Tool Selection by Task Type

```python
_TOOLS_BY_TYPE = {
    "design":    [read_file, write_file, list_directory],
    "implement": [read_file, write_file, append_file, list_directory],
    "test":      [read_file, write_file, append_file, list_directory, run_command],
    "review":    [read_file, write_file],
    "integrate": [read_file, write_file, append_file, list_directory, run_command],
    "configure": [read_file, write_file, list_directory, file_exists],
}

_DEFAULT_TOOLS = [read_file, write_file, list_directory]
```

**Least privilege** — agent only gets tools relevant to its task type.

### System Prompt Assembly

```python
def _build_system_prompt(task, dep_outputs) -> str:
    return f"""
You are an expert software engineer executing a single well-defined task.
Be thorough and complete. Always write all files to disk before finishing.

TASK ID:   {task['id']}
TASK TYPE: {task['task_type']}
TITLE:     {task['title']}

DESCRIPTION:
{task['description']}

FILES TO PRODUCE:
{output_files_list}

ACCEPTANCE CRITERIA (must satisfy ALL):
{criteria_list}

PRIOR TASK OUTPUTS (from dependencies):
{prior_context}
"""
```

### User Message (First Turn)

```python
user_message = (
    f"{task['description']}\n\n"
    "The project directory may be empty — there is no existing code to read.\n"
    "You must CREATE all output files from scratch using write_file.\n"
    "Do not spend time listing directories. Go directly to writing the output files."
)
```

---

## Agent Execution

```python
llm = init_chat_model(f"{provider}:{model}", temperature=0, max_tokens=3000)
agent = create_agent(llm, tools=tools, system_prompt=system_prompt)

final_state = None
async for step in agent.astream(
    {"messages": [{"role": "user", "content": user_message}]},
    stream_mode="values",
):
    last_msg = step["messages"][-1]
    tool_calls = getattr(last_msg, "tool_calls", None)
    if tool_calls:
        logger.info(f"Task {task['id']} → tool calls: {[tc['name'] for tc in tool_calls]}")
    else:
        logger.info(f"Task {task['id']} → {type(last_msg).__name__}: {str(last_msg.content)[:200]}")
    final_state = step
```

### Output Extraction

Handles both string content (OpenAI) and block list (Anthropic):

```python
def _get_content(msg) -> str:
    content = getattr(msg, "content", "")
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    return content or ""

# Walk backwards to find last non-empty AIMessage
output = next(
    (_get_content(msg) for msg in reversed(final_state["messages"])
     if type(msg).__name__ == "AIMessage" and _get_content(msg).strip()),
    ""
)

if not output.strip():
    raise ValueError("Agent returned empty output — no files written, no summary")
```

---

## LLM-as-Judge

### Verdict Schema

```python
class _JudgeVerdict(BaseModel):
    passed: bool
    score: int      # 0-10
    reason: str     # one sentence
```

### Judge Prompt

```python
_JUDGE_SYSTEM_PROMPT = """
You are a code review judge. Given a task description, its acceptance criteria,
and the AI agent's output, decide whether the task was completed satisfactorily.

Score 0-10:
 8-10 → passed (all acceptance criteria met)
 5-7  → borderline (minor gaps, still usable)
 0-4  → failed (criteria not met, re-execution needed)

Set passed=true if score >= 6. One short sentence for reason.
"""
```

### Judge Invocation

```python
async def _judge_task(task, agent_output) -> _JudgeVerdict:
    judge_model = config.get("llm", {}).get("judge_model", config["llm"]["model"])
    llm = init_chat_model(f"{provider}:{judge_model}", temperature=0, max_tokens=1000)
    
    judge_agent = create_agent(llm, tools=[], system_prompt=_JUDGE_SYSTEM_PROMPT, 
                               response_format=_JudgeVerdict)
    
    criteria = _parse_json_field(task.get("acceptance_criteria"))
    user_message = f"""TASK: {task['title']}
DESCRIPTION: {task['description']}
ACCEPTANCE CRITERIA: {json.dumps(criteria, indent=2)}

AGENT OUTPUT:
{agent_output[:2000]}"""

    result = await judge_agent.ainvoke({"messages": [{"role": "user", "content": user_message}]})
    return result["structured_response"]
```

### Judge Threshold & Retry

```python
verdict = await _judge_task(task, output)
logger.info(f"Judge verdict for {task['id']}: score={verdict.score}, passed={verdict.passed}, reason={verdict.reason}")

if not verdict.passed:
    raise ValueError(f"Judge rejected output (score={verdict.score}/10): {verdict.reason}")

return output  # passed → orchestrator stores as task.result
```

**Score < 6** → `ValueError` → orchestrator catches → `store.fail_task()` → retry logic.

---

## Configuration

```yaml
llm:
  provider: "anthropic"
  model: "claude-3-5-sonnet-20241022"
  judge_model: ""              # empty = use main model; set to cheaper model (e.g. haiku)
  temperature: 0
  max_tokens: 3000
```

---

## Logging

| Event | Log Level | Fields |
|-------|-----------|--------|
| Agent built | INFO | `task_id`, `task_type`, `tools=[names]` |
| Tool call | INFO | `task_id`, `tool_calls=[names]` |
| Agent message | INFO | `task_id`, `type`, `content[:200]` |
| Agent done | INFO | `task_id`, `output_chars` |
| Judge verdict | INFO | `task_id`, `score`, `passed`, `reason` |
| Judge fail | ERROR | (via ValueError → orchestrator logs) |

---

## Error Handling

| Failure | Throws | Handled By |
|---------|--------|------------|
| Empty agent output | `ValueError` | Orchestrator → retry |
| Judge score < 6 | `ValueError` | Orchestrator → retry |
| Tool error (write_file, etc.) | Exception from tool | LangGraph → orchestrator → retry |
| LLM API error | `APIError` | Orchestrator → retry |

---

## Extending the Executor

| Extension | How |
|-----------|-----|
| New task type | Add to `TaskType` enum + `_TOOLS_BY_TYPE` dict |
| Custom tools | Import in `_TOOLS_BY_TYPE` |
| Different judge prompt | Edit `_JUDGE_SYSTEM_PROMPT` |
| Structured output schema | Change `_JudgeVerdict` + prompt |
| Per-task judge model | Add `judge_model` to task row |
| Human review gate | Insert async human callback before judge |

---

## Testing the Executor

```python
# Unit test for judge
@pytest.mark.asyncio
async def test_judge_passes_good_output():
    task = {"title": "Create README", "description": "...", 
            "acceptance_criteria": json.dumps(["File exists", "Has title"])}
    output = "Created README.md with project title and usage section."
    verdict = await _judge_task(task, output)
    assert verdict.passed == True
    assert verdict.score >= 6

# Integration test (requires LLM)
@pytest.mark.asyncio
async def test_run_simple_task():
    task = make_task("test_001", "implement", "Create hello.py", 
                     output_files=["hello.py"], 
                     criteria=["File exists", "Prints hello"])
    result = await run_subtask_agent(task, dep_outputs=[])
    assert "hello.py" in result
```