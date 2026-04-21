# Operator Frontend

This directory is the repo-local boundary for the future operator console.
It now contains a minimal Vite, React, and TypeScript app shell plus reusable
UI-facing contracts.

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

## Commands

```bash
npm install
npm run typecheck
npm run build
npm run dev
```

The built app is served by the Python API service at `/operator`. Vite emits
asset URLs under `/operator/`, so run `npm run build` before using the preview
route through `slack-mirror api serve`.

## Current Files

- `src/contracts/selectedResults.ts`: selected candidate, context, artifact, and
  report-view contracts.
- `src/contracts/index.ts`: export surface for future frontend code.
- `src/components/OperatorShell.tsx`: first shell and navigation primitive.
- `src/components/MetricStrip.tsx`: semantic metric-strip primitive.
- `src/features/tenants/TenantWorkbench.tsx`: read-only tenant status adapter
  over `/v1/tenants`.
- `src/theme/`: CSS variable tokens and app-shell styling.
