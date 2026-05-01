# Agent Skills Pack (Repo-bundled)

This repo now includes an installable Slack Mirror skill pack under:

- `agent-skills/`

Included skills:
- `slack-mirror-orchestrator` (top-level router)
- `slack-mirror-live-ops`
- `slack-mirror-ingest`
- `slack-mirror-search`
- `slack-mirror-export`
- `slack-mirror-send`

Example prompts these skills are intended to support:

- "Send Michael a note about this on the SoyLei tenant from my user account."
- "What did Baker say about amazon today?"
- "Find the thread about the website outage in SoyLei and export the context."

## Install to local agent runtimes

Use the installer script:

```bash
scripts/install_agent_skills.sh
```

By default it installs to these locations (creating them if needed):
- `~/.openclaw/skills`
- `~/.codex/skills`
- `~/.gemini/skills`

## Custom targets

```bash
scripts/install_agent_skills.sh --target ~/.openclaw/skills --target ~/.codex/skills
```

## Dry run

```bash
scripts/install_agent_skills.sh --dry-run
```

## Notes

- Skills are plain skill folders with `SKILL.md` frontmatter and markdown instructions.
- The installer synchronizes only the repo-owned Slack Mirror skill folders, preserving unrelated skills in the target runtime.
- `slack-mirror-send` describes real outbound writes. Agents should use Slack Mirror MCP tools when available, include an idempotency key, and set `options.auth_mode="user"` when the user explicitly asks to send from their user account.
