# 0150 | Agent skills for Slack Mirror MCP workflows

State: CLOSED

Roadmap: P11

## Context

The user wants agent prompts such as "Send Michael a note about this on the
SoyLei tenant from my user account" and "What did Baker say about amazon today?"
to route through Slack Mirror reliably. The repo already bundles agent skills
under `agent-skills/`, but the existing set did not include a dedicated outbound
send skill and the search skill did not spell out person/date workflows.

## Current State

Shipped baseline:

- Slack Mirror exposes managed MCP tools for health, runtime status, workspace
  status, corpus search, conversation discovery/search, context packs, outbound
  message sends, and thread replies.
- Repo-bundled skills already exist for orchestration, ingest, live ops, search,
  and export.
- `scripts/install_agent_skills.sh` installs repo-bundled skills into local
  agent runtimes.

Shipped in this slice:

- Added `slack-mirror-send` for real outbound Slack messages, DM-style user
  targets, thread replies, bot-vs-user auth mode, and idempotency keys.
- Updated `slack-mirror-search` with MCP-first guidance for person/date queries
  such as "What did Baker say about amazon today?"
- Updated the orchestrator skill to route outbound sends.
- Hardened the skill installer so it only synchronizes repo-owned Slack Mirror
  skill folders and preserves unrelated runtime skills.
- Installed the updated skills into `~/.codex/skills`, `~/.openclaw/skills`,
  and `~/.gemini/skills`.

## Scope

- Update repo-bundled skills and installer docs.
- Keep the skills aligned with existing MCP/API behavior.
- Validate skill frontmatter and installer behavior.

## Non-Goals

- Do not add new MCP tools in this slice.
- Do not perform real outbound Slack sends during validation.
- Do not make agent skills store secrets or tenant credentials.

## Acceptance

- Agents have a dedicated Slack Mirror send skill that explains `workspace`,
  `channel_ref`, `options.auth_mode`, and `options.idempotency_key`.
- Search skill covers person/date/tenant requests and context expansion.
- Installer preserves unrelated skills in target directories.
- Planning audit and whitespace checks pass.

## Validation

Passed:

- `bash -n scripts/install_agent_skills.sh`
- `scripts/install_agent_skills.sh --dry-run`
- temp-target install smoke preserving an unrelated skill folder
- `./.venv/bin/python -m py_compile` over the skill frontmatter validation snippet
- `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
- `git diff --check`

## Next Recommended Action

Run a no-write connected MCP rehearsal in a fresh agent session to confirm the
new skills trigger for search and send prompts, then perform one explicitly
approved idempotent DM send if the user wants live proof.
