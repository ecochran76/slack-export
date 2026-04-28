# 0132 | Release candidate version cut

State: CLOSED

Roadmap: P11

## Purpose

Move the first stable MCP-capable user-scoped release candidate from the
development version to a non-development package version and validate it with
the strict release gate.

## Current State

The managed runtime and full MCP release-smoke pass completed under `0131`.
The strict release gate still failed on the clean committed baseline because
`pyproject.toml` advertised `0.2.0-dev`, which is intentionally rejected by
`--require-release-version`.

## Scope

- Update the canonical package version in `pyproject.toml` from `0.2.0-dev` to
  `0.2.0`.
- Keep `pyproject.toml` as the only manually edited version source.
- Commit the version/documentation slice before running the strict clean gate.
- Run `slack-mirror release check --require-clean --require-release-version
  --require-managed-runtime --json`.

## Non-goals

- Do not create a git tag in this slice.
- Do not publish packages or installers.
- Do not move the repo back to the next development version until the release
  decision/tagging step is complete.
- Do not change command surfaces or regenerate CLI docs unless the release gate
  reports they are stale.

## Acceptance

- Runtime package metadata resolves to `0.2.0`.
- The strict release gate passes on a clean worktree.
- Any release-blocking residual risks are documented.

## Status

CLOSED. The canonical package version is `0.2.0`. The strict clean
managed-runtime release gate is the validation for this slice.
