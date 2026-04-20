# 0065 | Tenant Semantic Readiness Diagnostics

State: CLOSED

Roadmap: P10

## Current State

- `0064` added retrieval profiles and read-only rollout planning.
- `search_readiness` reports configured-model coverage, but it is tied to the global semantic config rather than all named profiles.
- Operators can plan rollout for one profile, but cannot yet see a compact tenant readiness matrix across profiles.
- API, MCP, and browser surfaces do not yet expose the profile readiness states in the same terms as the CLI.

## Scope

- Add shared tenant semantic readiness diagnostics over named retrieval profiles.
- Surface profile readiness through CLI, API, MCP, and the authenticated browser.
- Keep the payload thin over the existing profile and rollout-plan logic.
- Preserve current search defaults and avoid running backfills automatically.

## Non-Goals

- Do not run semantic backfills in this slice.
- Do not promote `local-bge` or learned reranking as a default.
- Do not redesign the full search UI.
- Do not implement query-fusion changes or result actionability.

## Acceptance Criteria

- Operators can list semantic readiness for one workspace or all enabled workspaces.
- Each profile reports a clear state such as `ready`, `rollout_needed`, or `provider_unavailable`.
- API and MCP return the same readiness payload shape as CLI JSON.
- The tenant settings page exposes compact semantic readiness status per tenant without duplicating backend logic.
- Docs, roadmap, runbook, and tests are updated.

## Definition Of Done

- Code, docs, generated CLI reference, roadmap, and runbook are updated.
- Targeted CLI/API/MCP/service tests cover the new readiness surface.
- Planning audit passes.

## Closure Notes

- Added shared semantic-readiness diagnostics over named retrieval profiles.
- Added `search semantic-readiness` for one workspace or all enabled workspaces.
- Added API routes for profile listing and semantic readiness.
- Added MCP tools `search.profiles` and `search.semantic_readiness`.
- Added compact semantic-readiness rendering on authenticated tenant cards.
- Live smoke showed `default` baseline coverage is nearly complete but technically partial by three new messages, while `local-bge` still needs rollout.
