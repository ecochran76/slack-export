# Release Discipline

The supported repo-level release gate is:

```bash
slack-mirror release check
```

This checks:

- canonical version source-of-truth consistency between `pyproject.toml` and runtime `slack_mirror.__version__`
- generated CLI docs freshness
- planning-contract audit wiring

By default the planning audit helper is discovered from:

- `SLACK_MIRROR_PLANNING_AUDIT` if set
- the repo-local `scripts/audit_planning_contract.py`
- a sibling `agent-policies/repo-policy-selector/scripts/audit_planning_contract.py`

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

Normal CI runs this command directly:

```bash
python -m slack_mirror.cli.main release check
```

That keeps docs freshness and planning-audit drift under the same supported gate instead of duplicating partial checks in workflow-only logic.

## Supported Usage

Use the default gate during normal development:

```bash
slack-mirror release check
```

That is the expected check for:

- feature branches
- local maintenance work
- normal CI validation

Use the stricter gate for an actual release candidate:

```bash
slack-mirror release check --require-clean --require-release-version
```

That is the expected check immediately before tagging or publishing a non-development release.

## Release-Cut Sequence

The supported cut sequence is:

1. Update the canonical package version in `pyproject.toml` to the intended non-`-dev` release.
2. Regenerate and commit any required CLI docs if the command surface changed.
3. Run:

```bash
slack-mirror release check --require-clean --require-release-version
```

4. Cut the release or tag only after that strict check passes.
5. Move the repo back to the next development version in `pyproject.toml` when post-release development resumes.

Boundaries:

- this repo treats `pyproject.toml` as the only version source of truth to edit manually
- release readiness is defined by the supported gate, not by ad hoc combinations of tests and docs checks
- the strict cut flow is intentionally repo-level and does not try to automate tagging or publishing policy beyond validation
