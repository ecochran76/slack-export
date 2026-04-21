# Operator Frontend Contracts

This directory is the first repo-local boundary for the future operator console.
It is intentionally contract-first: no Vite app, React runtime, or package
build pipeline is introduced yet.

The current purpose is to model the selected-result workflow that is now stable
enough to inform shared UI primitives:

- search results expose selectable action targets
- selected targets can be expanded into context packs
- selected targets can be persisted as managed `selected-results` artifacts
- reports render from neutral JSON and should be portable across Slack, SMS /
  WhatsApp, and email surfaces

Shared type names avoid Slack-specific nouns. Repo-local adapters can still map
Slack fields such as workspace, channel, timestamp, and file IDs into the neutral
types.

## Boundary

`frontend/src/contracts/` is UI-facing and provider-neutral. It should remain
extractable into a future shared communications UI package after at least one
sibling repo proves the same model.

Repo-local Slack API clients and route implementations remain outside this
directory.

## Current Files

- `src/contracts/selectedResults.ts`: selected candidate, context, artifact, and
  report-view contracts.
- `src/contracts/index.ts`: export surface for future frontend code.
