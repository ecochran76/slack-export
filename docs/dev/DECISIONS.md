# Architectural Decisions

## ADR-0001: Evolve to Multi-Workspace Mirror Platform
- **Status:** Accepted
- **Date:** 2026-02-23
- **Decision:** Reframe project from point-in-time exporter to continuous mirror with per-workspace isolation.
- **Rationale:** Supports active workspace synchronization and long-lived local cache/search use cases.

## ADR-0002: SQLite as Primary Local Store
- **Status:** Accepted
- **Date:** 2026-02-23
- **Decision:** Use SQLite as the canonical local DB, including FTS indexes.
- **Rationale:** Portable, zero external dependency, sufficient for initial scale.

## ADR-0003: Hybrid Sync Model
- **Status:** Accepted
- **Date:** 2026-02-23
- **Decision:** Use webhooks/events for freshness and periodic reconciliation for correctness.
- **Rationale:** Events alone are insufficient under outages/rate limits; reconciliation guarantees eventual consistency.

## ADR-0004: Documentation Split
- **Status:** Accepted
- **Date:** 2026-02-23
- **Decision:** Place planning/dev notes in `docs/dev/` and user-facing docs in `docs/`.
- **Rationale:** Keeps operator/developer detail separate from user guidance.

## ADR-0005: External Channel Tool Integration
- **Status:** Proposed
- **Date:** 2026-02-23
- **Decision:** Integrate `~/.openclaw/workspace/scripts/slack_channels` via adapter layer.
- **Rationale:** Reuse existing channel-management capabilities and local mappings.
- **Open Questions:** Ownership of source-of-truth for channel map (script JSON vs DB).
