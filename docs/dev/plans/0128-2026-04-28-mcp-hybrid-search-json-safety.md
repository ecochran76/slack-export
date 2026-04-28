# 0128 | MCP hybrid search JSON safety

State: CLOSED

Roadmap: P11

## Purpose

Fix the MCP `search.corpus` failure exposed by the Lei banter harvest workflow:
hybrid all-workspace search could return bytes-like embedding fields and fail
MCP JSON serialization before the agent received any result rows.

## Current State

Slack Mirror already exposes corpus search through CLI, API, and MCP, including
all-workspace hybrid mode. A live reproduction of the handoff query showed the
MCP-breaking field was `results[0].embedding_blob`, a private binary embedding
blob retained by derived-text semantic results after scoring.

## Scope

- Strip `embedding_blob` from derived-text semantic search rows after scoring.
- Add MCP-side defensive conversion for bytes-like payloads so a future missed
  private blob is omitted rather than breaking the whole MCP response.
- Add targeted regression tests for derived-text semantic rows and MCP search
  response JSON safety.
- Keep the Lei handoff note focused on Slack Export tooling issues and source
  pointers, not detailed private banter-style guidance.

## Non-goals

- Do not add a new conversation discovery MCP tool in this slice.
- Do not change search ranking, retrieval profiles, or semantic scoring.
- Do not store raw private Slack message bodies or detailed persona training
  guidance in Slack Export planning history.

## Acceptance

- The reported all-workspace hybrid query shape is JSON-serializable.
- MCP `search.corpus` can render a result payload containing a bytes-like field
  without raising `TypeError`.
- Targeted search/MCP tests pass.
- Planning audit and `git diff --check` pass.

## Status

CLOSED. The binary field is removed at the derived-text semantic source, MCP
now defensively omits bytes-like values, and the handoff has been converted
into this bounded release-hardening slice.
