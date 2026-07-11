# 🤖 Human-in-the-Loop for GitHub Actions

The agent uses **Human-in-the-Loop (HITL)** middleware to pause execution before running dangerous tools (shell commands, file writes, GitHub API calls). This works locally with an interactive terminal prompt, but **hangs indefinitely in GitHub Actions** (no TTY).

This document explains the GitHub Actions-compatible HITL integration.

---

## 🔴 Problem

```python
# orchestrator.py - Local interactive terminal (works locally, HANGS in CI)
choice = Prompt.ask("Approve / Edit / Reject?", choices=["a", "e", "r"])
```

In GitHub Actions:
- No interactive stdin/stdout
- `rich.Prompt.ask()` blocks forever
- Workflow times out after 60 minutes default

---

## ✅ Solution: Three Approaches

| Approach | Mechanism | Best For | Permissions |
|----------|-----------|----------|-------------|
| **1. Environment Protection Rules** | Workflow pauses at `environment: production`; reviewers click Approve/Reject in GitHub UI | Production deployments, compliance | `id-token: write` + Environment config |
| **2. PR/Issue Comment Polling** | Bot posts comment with `/APPROVE`, `/REJECT`, `/EDIT`; polls every 15s | General CI, standard `GITHUB_TOKEN` | `issues: write` |
| **3. GitHub Gist** | Private Gist stores approval state; polls for updates | Fork PRs, minimal permissions | `gist` scope token |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    LangGraph Agent                              │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  HumanInTheLoopMiddleware (factory.py:interrupt_on)      │   │
│  │  - Intercepts tool calls matching interrupt_on keys      │   │
│  │  - Emits Interrupt with action_requests                  │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Orchestrator (orchestrator.py)               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  _in_github_actions() → GITHUB_ACTIONS=true               │   │
│  │  if CI: handle_query_github_hitl()                        │   │
│  │  else: _resolve_interrupt() via rich.Prompt               │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
    ┌─────────────────────────┐    ┌─────────────────────────┐
    │  Local Terminal         │    │  GitHub Actions         │
    │  rich.Prompt.ask()      │    │  GitHubActionsHITL      │
    │  → approve/edit/reject  │    │  → posts to Issue/Gist  │
    │                         │    │  → polls for decision   │
    └─────────────────────────┘    └─────────────────────────┘
```

---

## 📦 Key Components

### `hitl_github_actions.py`

| Class | Purpose |
|-------|---------|
| `ApprovalRequest` | Dataclass for pending approval (thread_id, tool_name, tool_args, allowed_decisions, etc.) |
| `GitHubApprovalStore` | Persistence layer (Issue Comments or Gist backend) |
| `GitHubActionsHITL` | Main handler: interrupt → post to GitHub → poll → resume |
| `handle_query_github_hitl()` | Drop-in replacement for `orchestrator.handle_query()` |

### `factory.py`

```python
interrupt_on = {
    "run_command": {"allowed_decisions": ["approve", "edit", "reject"]},
    "run_in_directory": {"allowed_decisions": ["approve", "edit", "reject"]},
    "write_file": {"allowed_decisions": ["approve", "edit", "reject"]},
    "append_file": {"allowed_decisions": ["approve", "edit", "reject"]},
    # All GitHub MCP tools added dynamically
}
```

### `orchestrator.py`

```python
def _in_github_actions() -> bool:
    return os.getenv("GITHUB_ACTIONS") == "true"

# Routes to appropriate handler
if _in_github_actions() and HITL_GITHUB_AVAILABLE:
    return await handle_query_github_hitl(agent, question, thread_id)
# else: local rich.Prompt handler
```

---

## 🚀 Usage

### 1. Install Dependencies

```bash
pip install httpx langgraph
```

### 2. Workflow File (Comment Polling - Default)

Save as `.github/workflows/agent.yml`:

```yaml
name: Agent with HITL

on:
  workflow_dispatch:
    inputs:
      question:
        description: 'Question for the agent'
        required: true
        type: string

permissions:
  contents: read
  issues: write        # Required for comment polling

jobs:
  agent:
    runs-on: ubuntu-latest
    timeout-minutes: 60

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -e .
          pip install httpx langgraph langchain

      - name: Run agent with HITL
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          QUESTION: ${{ github.event.inputs.question }}
        run: |
          python -c "
          import asyncio, os
          from educosys_claude.agent.factory import build_agent
          from educosys_claude.agent.hitl_github_actions import handle_query_github_hitl
          from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
          from educosys_claude.memory.short_term import get_checkpointer_db_path

          async def main():
              async with AsyncSqliteSaver.from_conn_string(get_checkpointer_db_path()) as checkpointer:
                  agent = await build_agent(checkpointer)
                  thread_id = f'github-actions-{os.getpid()}'
                  answer = await handle_query_github_hitl(agent, os.getenv('QUESTION'), thread_id)
                  print(answer)

          asyncio.run(main())
          "
```

### 3. Trigger Workflow

```bash
gh workflow run agent.yml -f question="Create a PR adding a README"
```

### 4. Human Approval

1. Workflow runs, agent needs approval for tool call
2. Bot posts comment on issue `HITL-TRACKING-{thread_id}`:
   ```
   ## 🤖 Human Approval Required
   **Thread:** `github-actions-12345` | **Tool:** `create_pull_request`
   
   ### Tool Arguments
   ```json
   {"title": "Add README", "body": "..."}
   ```
   
   ### Allowed Decisions
   `/APPROVE` / `/REJECT` / `/EDIT`
   
   *Reply with `/APPROVE`, `/REJECT [reason]`, or `/EDIT {"key": "value"}`*
   ```
3. Reviewer replies with `/APPROVE`
4. Workflow resumes, tool executes

---

## ⚙️ Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GITHUB_TOKEN` | Yes | GitHub token (auto-set as `${{ secrets.GITHUB_TOKEN }}`) |
| `GITHUB_REPOSITORY` | Yes | `owner/repo` (auto-set as `${{ github.repository }}`) |
| `GITHUB_GIST_ID` | No | Existing Gist ID for Gist backend |

### Approach Selection

```python
# In hitl_github_actions.py - GitHubActionsHITL constructor
hitl = GitHubActionsHITL(
    repo="owner/repo",
    token=os.getenv("GITHUB_TOKEN"),
    use_environment_approval=False,  # True = Pattern 1, False = Pattern 2/3
    environment="production",         # Only used if use_environment_approval=True
)

# Or use Gist backend
store = GitHubApprovalStore(
    repo="owner/repo",
    token=os.getenv("GITHUB_TOKEN"),
    use_gist=True,
    gist_id="abc123",
)
```

---

## 📝 Decision Commands

| Command | Format | Example |
|---------|--------|---------|
| **Approve** | `/APPROVE` | `/APPROVE` |
| **Reject** | `/REJECT [reason]` | `/REJECT Dangerous command` |
| **Edit** | `/EDIT {"key": "value"}` | `/EDIT {"command": "ls -la"}` |

---

## 🔒 Required Permissions

### Comment Polling (Default)
```yaml
permissions:
  contents: read
  issues: write    # Create tracking issue + post comments
```

### Environment Protection
```yaml
permissions:
  contents: read
  id-token: write  # For OIDC token to environment
```
Plus: Configure "production" environment in GitHub repo settings → Environments → Required reviewers

### Gist Backend
```yaml
permissions:
  contents: read
```
Plus: Token with `gist` scope (create PAT with gist access, store as secret)

---

## 🛠️ Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| Workflow hangs | No TTY in CI, local prompt used | Ensure `GITHUB_ACTIONS=true` detected |
| "Permission denied" posting comment | Missing `issues: write` | Add `issues: write` to permissions |
| Timeout after 60min | Human didn't respond | Increase `timeout-minutes` or reduce `poll_interval` |
| Gist not found | `GITHUB_GIST_ID` invalid | Create private gist, add ID to env |
| Decision not detected | Comment format wrong | Use exact `/APPROVE`, `/REJECT`, `/EDIT` |

---

## 📁 File Reference

```
educosys_claude/agent/
├── factory.py                    # interrupt_on config, HITL middleware
├── orchestrator.py               # Auto-detects CI, routes to handler
├── hitl_github_actions.py        # GitHub Actions HITL implementation
│   ├── ApprovalRequest
│   ├── GitHubApprovalStore       # Issue Comments / Gist backends
│   ├── GitHubActionsHITL         # Main handler
│   ├── handle_query_github_hitl  # Drop-in replacement
│   └── GITHUB_ACTIONS_WORKFLOW   # Complete workflow YAML (print via __main__)
└── tools.py                      # Tool definitions (search_codebase, etc.)
```

---

## 🎯 Quick Test Locally (Simulate CI)

```bash
# Simulate GitHub Actions environment
GITHUB_ACTIONS=true GITHUB_TOKEN=ghp_xxx GITHUB_REPOSITORY=owner/repo \
python -m educosys_claude.agent.hitl_github_actions
```

Outputs the workflow YAML for copy-paste.

---

## 🔗 Related Docs

- [Agent Package](AGENT_PACKAGE.md) - Full agent architecture
- [Middleware Package](MIDDLEWARE_PACKAGE.md) - HITL middleware internals
- [Tools Package](TOOLS_PACKAGE.md) - Dangerous tools requiring approval
- [Memory Package](MEMORY_PACKAGE.md) - Session persistence for HITL resume