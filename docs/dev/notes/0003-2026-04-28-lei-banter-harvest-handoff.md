# Lei Banter Harvest Handoff

Date: 2026-04-28

## Purpose

OpenClaw is tuning the SoyLei company agent, Lei, to match internal SoyLei
banter style for authorized users Eric, Michael, and Baker.

This note records the Slack Mirror evidence path used during the harvest and
the Slack Export follow-ups exposed by that workflow.

## Runtime Context

Reviewed from OpenClaw home:

- `/home/ecochran76/.openclaw/workspace-soylei-primary/SOUL.md`
- `/home/ecochran76/.openclaw/notes/soylei/knowledge-sources.md`
- `/home/ecochran76/.openclaw/notes/soylei/lei-banter-style.json`

The resulting OpenClaw artifact is:

- `/home/ecochran76/.openclaw/notes/soylei/lei-banter-style.json`

That artifact stores reviewed, reusable style patterns and source pointers. It
does not dump raw private chat transcripts into OpenClaw notes.

## Slack Mirror Evidence Used

MCP readiness checks showed both workspaces indexed and ready:

- `soylei`: 19,153 messages, configured `local-hash-128` embeddings ready
- `default`: 92,328 messages, configured `local-hash-128` embeddings ready

The useful style source was SoyLei MPDM traffic involving Eric, Michael, and
Baker, especially:

- `mpdm-bakermaun--ecochran76--michael.j.forrester-1`
- related historical SoyLei MPDMs including Michael, Baker, Nacu, Austin, and
  Eric
- lower-priority default workspace MPDMs involving Eric, Baker, and Michael

Primary local export packets consulted:

- `exports/day_exports/soylei__mpdm-bakermaun--ecochran76--michael.j.forrester-1__2025-06-25__nacu_scope.json`
- `exports/day_exports/soylei__mpdm-bakermaun--ecochran76--michael.j.forrester-1__2025-07-28.html`
- `exports/day_exports/soylei__mpdm-bakermaun--ecochran76--michael.j.forrester-1__2025-07-31__nacu_scope.json`
- `exports/day_exports/default__mpdm-ecochran--vgarg--bwkuehl--mf1-1__2026-01-14.json`
- `exports/day_exports/default__mpdm-mf1--ecochran--bwkuehl-1__2024-09-03__nacu_scope.json`

## Slack Export Boundary

The reviewed style conclusions belong in the OpenClaw artifact listed above,
not in Slack Export planning history. This repo should retain only the source
pointers and tool follow-ups needed to make future authorized review workflows
less dependent on manual filesystem inspection.

## Slack Export Issues Exposed

1. Hybrid all-workspace corpus search failed through the Slack Mirror MCP tool:

```text
Object of type bytes is not JSON serializable
```

The failing call shape was:

```json
{
  "all_workspaces": true,
  "mode": "hybrid",
  "query": "Eric Baker Michael dip stick ass hat short baby face lube SoyLei",
  "limit": 20
}
```

Lexical workspace-scoped searches worked, so the harvest continued using
workspace-scoped lexical search plus existing local day exports.

2. The currently exposed MCP search surface was not sufficient by itself for
channel-level style review. The workflow needed local export files to inspect
full MPDM day context and identify the most useful source packets.

## Suggested Slack Export Follow-ups

1. Fix the MCP serialization failure for hybrid `search.corpus` with
   `all_workspaces=true`, or normalize bytes-like fields before returning MCP
   JSON. This was promoted to:
   `docs/dev/plans/0128-2026-04-28-mcp-hybrid-search-json-safety.md`
2. Add or expose a narrow conversation/channel discovery surface suitable for
   agents, with filters for workspace, channel type, display name, and member
   labels. This would avoid using prior daily summaries or local filesystem
   searches to discover MPDM candidates.
3. Improve guidance/ergonomics around the existing bounded context/export
   helpers (`search.context_pack` and `search.context_export`) so agents can
   move from selected corpus results to adjacent-message review without manual
   `exports/day_exports` filesystem inspection.
4. Keep raw private-chat bodies out of downstream memory handoffs by default;
   prefer source pointers plus distilled, reviewed style patterns.

## OpenClaw Follow-up

After the OpenClaw live patch for cron task recovery is applied and settled,
check the SoyLei daily WhatsApp/chat harvesting timer. The expected outcome is
that the timer reviews the day's SoyLei chats and writes both:

- OpenClaw-style memory candidates
- Graphiti-style relationship/fact candidates

This reminder is also recorded in:

- `/home/ecochran76/.openclaw/notes/soylei/lei-banter-style.json`

## Validation

Completed during note creation:

- Confirmed Slack Mirror readiness for `soylei` and `default` via MCP.
- Confirmed the OpenClaw banter JSON validates with `jq empty`.
- Confirmed OpenClaw config still validates with `openclaw config validate`.

Repo-local validation for this handoff note:

- `git diff --check`

## Status

RECORDED. Lei has a deterministic OpenClaw-side banter style artifact. The
Slack Export serialization defect was promoted to plan `0128`; remaining
future work is agent-friendly MPDM discovery and clearer context/export helper
ergonomics.
