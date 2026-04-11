# Release Discipline

The supported repo-level release gate is:

```bash
slack-mirror release check
```

This checks:

- canonical version source-of-truth consistency between `pyproject.toml` and runtime `slack_mirror.__version__`
- generated CLI docs freshness
- planning-contract audit wiring

For an actual cut candidate, use the stricter form:

```bash
slack-mirror release check --require-clean --require-release-version
```

That additionally fails when:

- the git worktree is dirty
- the package version is still a development version such as `*-dev`

Release policy boundaries:

- `pyproject.toml` is the canonical version source of truth
- MCP server metadata must advertise the same runtime version as the package
- generated CLI docs must be committed as part of release-affecting CLI changes
- planning wiring must remain valid under the canonical roadmap/runbook/plan contract

This command is the supported release-readiness checklist entrypoint. If release discipline changes, update this file and the command in the same slice.
