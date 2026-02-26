# Agent Skills Pack (Repo-bundled)

This repo now includes an installable Slack Mirror skill pack under:

- `agent-skills/`

Included skills:
- `slack-mirror-orchestrator` (top-level router)
- `slack-mirror-live-ops`
- `slack-mirror-ingest`
- `slack-mirror-search`
- `slack-mirror-export`

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
- The installer uses `rsync --delete` per target so target skill folders match repo contents exactly.
