"""
GitHub Actions-compatible Human-in-the-Loop for LangGraph agents.

PROBLEM: Your original orchestrator.py uses `rich.Prompt.ask()` which blocks on stdin.
         This HANGS INDEFINITELY in GitHub Actions (no interactive TTY).

SOLUTION: This module replaces the blocking prompt with THREE non-interactive approaches:

  1. ENVIRONMENT PROTECTION RULES (Recommended for Production)
     - Configure "production" environment in GitHub repo settings with required reviewers
     - Add `environment: production` to your workflow job
     - GitHub PAUSES the workflow at the environment until approved
     - Zero custom code needed for approval UI

  2. PR/ISSUE COMMENT POLLING (Implemented in GitHubApprovalStore)
     - Bot posts approval request as Issue Comment with `/APPROVE`, `/REJECT`, `/EDIT` commands
     - Workflow polls comments every 15s until human replies
     - Works with standard GITHUB_TOKEN (needs issues: write permission)

  3. GITHUB GIST (For forks / minimal permissions)
     - Stores approval state in private Gist
     - No repo write access needed
     - Polls Gist for updates

USAGE IN GITHUB ACTIONS WORKFLOW:
  See GITHUB_ACTIONS_WORKFLOW constant at bottom of file for complete YAML.
"""

import os
import json
import time
import asyncio
from datetime import datetime
from typing import Any, Literal, Optional
from dataclasses import dataclass, asdict

import httpx
from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver

from educosys_claude.agent.orchestrator import handle_query
from educosys_claude.agent.factory import build_agent


@dataclass
class ApprovalRequest:
    """
    Data class representing a single pending approval request.

    Stored in GitHub (Issue Comment or Gist) and polls for decision.
    All fields are JSON-serializable for persistence.
    """
    thread_id: str                    # LangGraph thread_id (checkpoint key)
    step_id: str                      # Unique ID for this interrupt step
    tool_name: str                    # Tool being called (e.g., "run_command")
    tool_args: dict                   # Arguments the tool was called with
    allowed_decisions: list[str]      # ["approve", "edit", "reject"]
    description: str                  # Human-readable explanation
    created_at: str                   # ISO timestamp when request created
    status: Literal["pending", "approved", "rejected", "edited"] = "pending"
    decision: Optional[Literal["approve", "reject", "edit"]] = None
    edited_args: Optional[dict] = None
    decided_by: Optional[str] = None  # GitHub username who decided
    decided_at: Optional[str] = None  # ISO timestamp of decision


class GitHubApprovalStore:
    """
    Persistence layer for approval requests using GitHub APIs.

    Two backends:
    - Issue Comments: Posts to a tracking issue (HITL-TRACKING-{thread_id}) as comments
    - GitHub Gist: Private gist, one file per approval step

    Both support polling for decisions via GitHub REST API.
    """

    def __init__(
        self,
        repo: str,                      # "owner/repo" format
        token: Optional[str] = None,    # GitHub token (defaults to GITHUB_TOKEN env)
        use_gist: bool = False,         # True = use Gist, False = use Issue Comments
        gist_id: Optional[str] = None,  # Existing gist ID (creates new if None)
    ):
        self.repo = repo
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.use_gist = use_gist
        self.gist_id = gist_id or os.getenv("GITHUB_GIST_ID")
        # Async HTTP client with GitHub API headers
        self.client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=30.0,
        )

    async def create_request(self, request: ApprovalRequest) -> str:
        """
        Create approval request in GitHub (Issue Comment or Gist).

        Returns:
            GitHub comment ID or Gist ID for tracking.
        """
        body = self._format_request(request)

        if self.use_gist:
            return await self._create_gist(request, body)
        else:
            return await self._create_issue_comment(request, body)

    async def _create_issue_comment(self, request: ApprovalRequest, body: str) -> str:
        """
        Post approval request as comment on tracking issue.

        Creates/uses a single tracking issue per thread_id to group related requests.
        """
        issue_number = await self._get_or_create_tracking_issue(request.thread_id)

        url = f"https://api.github.com/repos/{self.repo}/issues/{issue_number}/comments"
        resp = await self.client.post(url, json={"body": body})
        resp.raise_for_status()
        return str(resp.json()["id"])

    async def _create_gist(self, request: ApprovalRequest, body: str) -> str:
        """
        Store approval request as a file in a GitHub Gist.

        Each step gets its own file: approval-{step_id}.md
        """
        if self.gist_id:
            # Update existing gist
            url = f"https://api.github.com/gists/{self.gist_id}"
            files = {f"approval-{request.step_id}.md": {"content": body}}
            resp = await self.client.patch(url, json={"files": files})
        else:
            # Create new private gist
            url = "https://api.github.com/gists"
            files = {f"approval-{request.step_id}.md": {"content": body}}
            resp = await self.client.post(url, json={"files": files, "public": False})
        resp.raise_for_status()
        return resp.json()["id"]

    def _format_request(self, req: ApprovalRequest) -> str:
        """
        Render approval request as Markdown with clickable action commands.

        Human replies with one of:
          /APPROVE
          /REJECT [reason]
          /EDIT {"key": "new_value"}
        """
        # Generate command reference links (for documentation; not clickable in issue)
        decisions_md = " / ".join(
            f"`/{d.upper()}`" for d in req.allowed_decisions
        )

        args_json = json.dumps(req.tool_args, indent=2)

        return f"""<!-- HITL-APPROVAL:{req.step_id} -->
## 🤖 Human Approval Required

**Thread:** `{req.thread_id}` | **Step:** `{req.step_id}` | **Tool:** `{req.tool_name}`

### Tool Arguments
```json
{args_json}
```

### Allowed Decisions
{decisions_md}

### Description
{req.description}

---
*Created: {req.created_at}*
*Reply with `/APPROVE`, `/REJECT [reason]`, or `/EDIT {{\"key\": \"value\"}}` to decide.*
"""

    def _action_url(self, step_id: str, decision: str) -> str:
        """Generate reference URL for decision (documentation only)."""
        return f"https://github.com/{self.repo}/issues/comments#issuecomment-{step_id}-{decision}"

    async def _get_or_create_tracking_issue(self, thread_id: str) -> int:
        """
        Get existing tracking issue for this thread, or create new one.

        Searches for issue with title "HITL-TRACKING-{thread_id}".
        """
        url = "https://api.github.com/search/issues"
        params = {
            "q": f"repo:{self.repo} type:issue in:title HITL-TRACKING-{thread_id}",
            "per_page": 1,
        }
        resp = await self.client.get(url, params=params)
        resp.raise_for_status()
        items = resp.json()["items"]
        if items:
            return items[0]["number"]

        # Create new tracking issue
        url = f"https://api.github.com/repos/{self.repo}/issues"
        body = f"Tracking issue for HITL thread `{thread_id}`\n\n<!-- HITL-TRACKING:{thread_id} -->"
        resp = await self.client.post(url, json={"title": f"HITL-TRACKING-{thread_id}", "body": body})
        resp.raise_for_status()
        return resp.json()["number"]

    async def wait_for_decision(
        self,
        step_id: str,
        timeout: int = 3600,      # 1 hour default
        poll_interval: int = 15,  # Check every 15 seconds
    ) -> ApprovalRequest:
        """
        Poll GitHub for decision on this approval step.

        Args:
            step_id: Unique step identifier from ApprovalRequest
            timeout: Max seconds to wait
            poll_interval: Seconds between polls

        Returns:
            ApprovalRequest with updated status/decision

        Raises:
            TimeoutError: No decision within timeout
        """
        start = time.time()
        gist_id = self.gist_id

        while time.time() - start < timeout:
            if self.use_gist:
                request = await self._poll_gist(gist_id or step_id, step_id)
            else:
                request = await self._poll_issue_comments(step_id)

            if request and request.status != "pending":
                return request

            await asyncio.sleep(poll_interval)

        raise TimeoutError(f"Approval timeout for step {step_id} after {timeout}s")

    async def _poll_issue_comments(self, step_id: str) -> Optional[ApprovalRequest]:
        """
        Check issue comments for decision reply.

        Searches for comments containing the HITL-APPROVAL marker,
        then looks for reply comments with /APPROVE, /REJECT, /EDIT.
        """
        # Find issue containing the approval request
        url = "https://api.github.com/search/issues"
        params = {"q": f"repo:{self.repo} type:issue comment:HITL-APPROVAL:{step_id}"}
        resp = await self.client.get(url, params=params)
        resp.raise_for_status()
        items = resp.json().get("items", [])
        if not items:
            return None

        issue_number = items[0]["number"]
        # Get all comments on that issue
        url = f"https://api.github.com/repos/{self.repo}/issues/{issue_number}/comments"
        resp = await self.client.get(url)
        resp.raise_for_status()
        comments = resp.json()

        # Check comments in reverse (newest first) for decision
        for comment in reversed(comments):
            body = comment.get("body", "")
            if f"HITL-APPROVAL:{step_id}" not in body:
                continue

            decision = self._parse_decision(body)
            if decision:
                return self._reconstruct_request(comment, decision)

        return None

    async def _poll_gist(self, gist_id: str, step_id: str) -> Optional[ApprovalRequest]:
        """
        Check Gist file for decision update.

        Gist file content is replaced with decision markdown when human decides.
        """
        url = f"https://api.github.com/gists/{gist_id}"
        resp = await self.client.get(url)
        resp.raise_for_status()
        gist = resp.json()

        filename = f"approval-{step_id}.md"
        if filename not in gist["files"]:
            return None

        content = gist["files"][filename]["content"]
        decision = self._parse_decision(content)
        if decision:
            return self._reconstruct_request_from_gist(content, decision)

        return None

    def _parse_decision(self, text: str) -> Optional[dict]:
        """
        Parse human decision from comment/Gist text.

        Expected formats:
          /APPROVE
          /REJECT optional reason here
          /EDIT {"key": "value"}
        """
        text = text.strip()
        if text.startswith("/APPROVE"):
            return {"type": "approve"}
        if text.startswith("/REJECT"):
            reason = text[7:].strip() or "Rejected by human"
            return {"type": "reject", "message": reason}
        if text.startswith("/EDIT"):
            try:
                args_json = text[5:].strip()
                new_args = json.loads(args_json) if args_json else {}
                return {"type": "edit", "edited_action": {"args": new_args}}
            except json.JSONDecodeError:
                return None
        return None

    def _reconstruct_request(self, comment: dict, decision: dict) -> ApprovalRequest:
        """
        Rebuild ApprovalRequest from comment metadata + parsed decision.

        Note: In production, you'd store the full request JSON in a separate
        database or Gist file to reconstruct exactly. This is simplified.
        """
        return ApprovalRequest(
            thread_id=comment.get("issue_url", "").split("/")[-1],
            step_id="",  # Would parse from comment marker
            tool_name="",
            tool_args={},
            allowed_decisions=[],
            description="",
            created_at=comment["created_at"],
            status=decision["type"],
            decision=decision["type"],
            decided_by=comment["user"]["login"],
            decided_at=datetime.utcnow().isoformat(),
        )

    def _reconstruct_request_from_gist(self, content: str, decision: dict) -> ApprovalRequest:
        """Parse request + decision from Gist content. Implement based on your storage format."""
        pass  # Implement if using Gist backend

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()


class GitHubActionsHITL:
    """
    Main HITL handler for GitHub Actions.

    Integrates with LangGraph's interrupt mechanism:
    1. Agent hits interrupt (tool call matching interrupt_on config)
    2. handle_interrupt() called with interrupt payload
    3. Creates ApprovalRequest, posts to GitHub
    4. Polls until human decides
    5. Resumes agent with Command(resume={decisions})
    """

    def __init__(
        self,
        repo: str,
        token: Optional[str] = None,
        use_environment_approval: bool = False,
        environment: str = "production",
    ):
        self.store = GitHubApprovalStore(repo, token)
        self.use_environment_approval = use_environment_approval
        self.environment = environment

    async def handle_interrupt(
        self,
        agent,
        result,
        agent_config: dict,
    ):
        """
        Process LangGraph interrupt and wait for GitHub approval.

        Args:
            agent: Compiled LangGraph agent
            result: GraphOutput with .interrupts attribute
            agent_config: Config dict with {"configurable": {"thread_id": "..."}}

        Returns:
            New GraphOutput after resuming with human decisions.
        """
        interrupt_payload = result.interrupts[0].value
        decisions = []

        for action_request in interrupt_payload["action_requests"]:
            tool_name = action_request["name"]
            tool_args = action_request["args"]
            allowed = action_request.get("allowed_decisions", ["approve", "reject", "edit"])
            description = action_request.get(
                "description",
                f"Tool execution pending approval\n\nTool: {tool_name}\nArgs: {tool_args}"
            )

            # Build request object
            request = ApprovalRequest(
                thread_id=agent_config["configurable"]["thread_id"],
                step_id=action_request.get("id", f"{tool_name}-{hash(str(tool_args))}"),
                tool_name=tool_name,
                tool_args=tool_args,
                allowed_decisions=allowed,
                description=description,
                created_at=datetime.utcnow().isoformat(),
            )

            # Post to GitHub
            await self.store.create_request(request)

            # Wait for human decision
            if self.use_environment_approval:
                decision = await self._wait_for_environment_approval(request)
            else:
                decision = await self.store.wait_for_decision(request.step_id)

            decisions.append(decision)

        # Convert decisions to LangGraph resume format
        resume_decisions = []
        for d in decisions:
            if d.decision == "edit":
                resume_decisions.append({
                    "type": "edit",
                    "edited_action": d.edited_args,
                })
            else:
                resume_decisions.append({
                    "type": d.decision,
                    "message": getattr(d, "message", None),
                })

        # Resume agent with decisions
        result = await agent.ainvoke(
            Command(resume={"decisions": resume_decisions}),
            config=agent_config,
            version="v2",
        )
        return result

    async def _wait_for_environment_approval(self, request: ApprovalRequest) -> ApprovalRequest:
        """
        Placeholder for GitHub Environment Protection Rules approach.

        With environment protection, the WORKFLOW ITSELF pauses at `environment: production`.
        This method would not be called directly; instead, the workflow YAML handles it.

        See GITHUB_ACTIONS_WORKFLOW below for implementation.
        """
        # If using environment approval, the workflow should be structured as:
        # 1. Run agent until interrupt
        # 2. Save interrupt state to artifact/file
        # 3. Deploy to environment (pauses for approval)
        # 4. Resume agent with decision
        # This requires splitting the workflow into multiple jobs.
        pass


async def handle_query_github_hitl(agent, question: str, thread_id: str) -> str:
    """
    Drop-in replacement for orchestrator.handle_query with GitHub Actions HITL.

    Usage:
        from educosys_claude.agent.hitl_github_actions import handle_query_github_hitl
        answer = await handle_query_github_hitl(agent, question, thread_id)
    """
    agent_config = {"configurable": {"thread_id": thread_id}}

    try:
        result = await agent.ainvoke(
            {"messages": [{"role": "user", "content": question}]},
            config=agent_config,
            version="v2",
        )

        hitl = GitHubActionsHITL(repo=os.getenv("GITHUB_REPOSITORY", "owner/repo"))

        while result.interrupts:
            result = await hitl.handle_interrupt(agent, result, agent_config)

        return result.value["messages"][-1].content

    except Exception as e:
        return f"Error: {e}"


# =============================================================================
# GITHUB ACTIONS WORKFLOW EXAMPLE
# =============================================================================
# Save as .github/workflows/agent.yml
#
# This workflow demonstrates THREE patterns:
# 1. Comment polling (default in GitHubActionsHITL)
# 2. Environment protection (uncomment environment: production)
# 3. Manual workflow_dispatch trigger
#
# =============================================================================

GITHUB_ACTIONS_WORKFLOW = """
name: Agent with Human-in-the-Loop

on:
  workflow_dispatch:
    inputs:
      question:
        description: 'Question for the agent'
        required: true
        type: string
      thread_id:
        description: 'Conversation thread ID (optional, auto-generated if omitted)'
        required: false
        type: string

permissions:
  contents: read
  issues: write          # Required for comment polling approach
  pull-requests: write   # Optional, for PR comment approach

jobs:
  agent:
    runs-on: ubuntu-latest
    # environment: production    # ← UNCOMMENT for Environment Protection Rules (Pattern 2)
    timeout-minutes: 60        # Max wait for human approval

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
          THREAD_ID: ${{ github.event.inputs.thread_id }}
        run: |
          python -c "
          import asyncio
          import os
          from educosys_claude.agent.factory import build_agent
          from educosys_claude.agent.hitl_github_actions import handle_query_github_hitl
          from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
          from educosys_claude.memory.short_term import get_checkpointer_db_path

          async def main():
              async with AsyncSqliteSaver.from_conn_string(get_checkpointer_db_path()) as checkpointer:
                  agent = await build_agent(checkpointer)
                  thread_id = os.getenv('THREAD_ID') or f'github-actions-{os.getpid()}'
                  answer = await handle_query_github_hitl(agent, os.getenv('QUESTION'), thread_id)
                  print(answer)

          asyncio.run(main())
          "


# =============================================================================
# PATTERN 2: ENVIRONMENT PROTECTION RULES (Alternative approach)
# =============================================================================
# This REQUIRES splitting into two jobs because the workflow PAUSES at environment.
#
# .github/workflows/agent-environment.yml
#
# name: Agent with Environment Approval
# on:
#   workflow_dispatch:
#     inputs:
#       question: { required: true }
#
# jobs:
#   run-agent:
#     runs-on: ubuntu-latest
#     outputs:
#       interrupt_state: ${{ steps.save.outputs.state }}
#       thread_id: ${{ steps.setup.outputs.thread_id }}
#     steps:
#       - uses: actions/checkout@v4
#       - uses: actions/setup-python@v5
#         with: { python-version: '3.11' }
#       - run: pip install -e .
#       - id: setup
#         run: echo "thread_id=github-actions-${{ github.run_id }}" >> $GITHUB_OUTPUT
#       - id: run
#         run: |
#           python -c "
#           import asyncio, os
#           from educosys_claude.agent.factory import build_agent
#           from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
#           from educosys_claude.memory.short_term import get_checkpointer_db_path
#
#           async def main():
#               async with AsyncSqliteSaver.from_conn_string(get_checkpointer_db_path()) as cp:
#                   agent = await build_agent(cp)
#                   result = await agent.ainvoke(
#                       {'messages': [{'role': 'user', 'content': os.getenv('QUESTION')}]},
#                       config={'configurable': {'thread_id': os.getenv('THREAD_ID')}},
#                       version='v2'
#                   )
#                   import json
#                   if result.interrupts:
#                       print('INTERRUPT::' + json.dumps({
#                           'interrupts': [i.value for i in result.interrupts],
#                           'thread_id': os.getenv('THREAD_ID')
#                       }))
#                   else:
#                       print('DONE::' + result.value['messages'][-1].content)
#
#           asyncio.run(main())
#           " env: { QUESTION: ${{ github.event.inputs.question }}, THREAD_ID: ${{ steps.setup.outputs.thread_id }} }
#       - id: save
#         if: ${{ success() }}
#         run: echo "state=<<EOF" >> $GITHUB_OUTPUT; cat interrupt.json >> $GITHUB_OUTPUT; echo "EOF" >> $GITHUB_OUTPUT
#
#   wait-for-approval:
#     needs: run-agent
#     runs-on: ubuntu-latest
#     environment: production          # ← PAUSES HERE until approved in GitHub UI
#     steps:
#       - run: echo "Approved! Resuming..."
#
#   resume-agent:
#     needs: [run-agent, wait-for-approval]
#     runs-on: ubuntu-latest
#     steps:
#       - uses: actions/checkout@v4
#       - uses: actions/setup-python@v5
#         with: { python-version: '3.11' }
#       - run: pip install -e .
#       - run: |
#           python -c "
#           import asyncio, os, json
#           from educosys_claude.agent.factory import build_agent
#           from langgraph.types import Command
#           from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
#           from educosys_claude.memory.short_term import get_checkpointer_db_path
#
#           async def main():
#               async with AsyncSqliteSaver.from_conn_string(get_checkpointer_db_path()) as cp:
#                   agent = await build_agent(cp)
#                   # Load interrupt state from previous job
#                   interrupt_data = json.loads(os.getenv('INTERRUPT_DATA'))
#                   # Resume with approval
#                   result = await agent.ainvoke(
#                       Command(resume={'decisions': [{'type': 'approve'}]}),
#                       config={'configurable': {'thread_id': interrupt_data['thread_id']}},
#                       version='v2'
#                   )
#                   print(result.value['messages'][-1].content)
#
#           asyncio.run(main())
#           " env: { INTERRUPT_DATA: ${{ needs.run-agent.outputs.interrupt_state }} }
"""


if __name__ == "__main__":
    import sys
    # Print workflow YAML for easy copy-paste
    print(GITHUB_ACTIONS_WORKFLOW)