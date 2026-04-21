# 0101 | React Tenant Detail Expansion

State: CLOSED

Roadmap: P09

## Current State

The React `/operator` preview is served behind the existing authenticated API
service and reads the live `/v1/tenants` status payload. Browser QA confirmed
that it renders the configured tenants and status data, but the diagnostic
detail block under every tenant is always expanded, making the workbench
vertically bulky before action controls have even migrated.

## Scope

- Keep the tenant workbench read-only.
- Preserve always-visible tenant identity, badges, DB metric strip, backfill
  status, live-sync status, and health status.
- Move lower-frequency diagnostics into an accessible per-tenant disclosure:
  live units, attachment/OCR text counts, embedding/derived-text errors, and
  semantic-readiness profile chips.
- Keep the collapsed summary high-density enough to communicate live-unit,
  text, and semantic-readiness state without opening the row.
- Validate the real served `/operator` page with `agent-browser`.

## Non-Goals

- No tenant activation, backfill, live-sync, or retirement mutations in React.
- No new API payload fields.
- No route, auth, or Python service behavior changes.
- No shared package extraction from this repo in this slice.

## Acceptance Criteria

- Tenant rows remain full-width.
- Critical status widgets remain visible without expansion.
- Each tenant has a keyboard-accessible details disclosure.
- Collapsed rows expose a concise diagnostic summary.
- Expanding a row reveals live units, text/embedding stats, and semantic profile
  chips.
- Desktop and mobile browser smoke show no horizontal overflow.

## Definition Of Done

- Frontend typecheck and production build pass.
- Planning audit passes.
- `agent-browser` confirms live tenants render, disclosures are present, a
  disclosure can be opened, and mobile overflow remains false.

## Completion Notes

- Added per-tenant native `<details>` disclosure around lower-frequency
  diagnostics.
- Added collapsed diagnostic summaries for live units, attachment/OCR text, and
  semantic-profile readiness.
- Added responsive disclosure styling that preserves the compact desktop row
  and stacks cleanly on mobile.
