# Live MCP Client Acceptance

State: CLOSED
Roadmap: P11
Opened: 2026-04-20
Closed: 2026-04-20

## Scope

Exercise the documented MCP release baseline from a real connected MCP client and record whether it behaves like a practical operator interface.

This slice covers:

- runtime and managed health tools
- workspace listing and workspace status tools
- corpus search and semantic-readiness tools
- listener lifecycle tools using a bounded internal listener record
- a controlled outbound-send decision, limited to Eric if performed
- release-gate and planning validation after the live acceptance pass

This slice does not include:

- adding new MCP tools unless acceptance exposes a concrete blocker
- broad semantic-search quality work
- frontend worktree changes
- sending messages to anyone except Eric

## Current State

- MCP protocol, tool listing, structured errors, runtime status, search tools, outbound tools, and listener tools are covered by unit tests
- managed install checks validate a real MCP stdio health probe plus bounded concurrent MCP wrapper launches
- `docs/API_MCP_CONTRACT.md` now documents the first-release MCP tool groups and preflight gates
- live acceptance from an actual configured MCP client exposed one release blocker:
  - MCP clients launched without `XDG_RUNTIME_DIR` or `DBUS_SESSION_BUS_ADDRESS` could falsely report active systemd user units as inactive
- shared `systemctl --user` status probes now rehydrate the user runtime/bus environment before querying service state

## Outcome

- the stripped-environment status repro now reports active API, daemon, webhook, and runtime-report timer units correctly
- the managed install was updated from this repo after the fix
- direct `~/.local/bin/slack-mirror-mcp` JSONL smoke with stripped DBus environment passed:
  - `initialize`
  - `tools/list`
  - `runtime.status`
  - `runtime.live_validation`
  - `search.semantic_readiness`
- connected MCP client checks passed for:
  - `health`
  - `runtime.report.latest`
  - `workspaces.list`
  - `workspace.status`
  - `search.readiness`
  - `search.corpus`
  - `search.health`
  - `listeners.register`
  - `listeners.status`
  - `listeners.list`
  - `deliveries.list`
  - `listeners.unregister`
  - `messages.send`
- one outbound acceptance message was sent only to Eric on `default`, using idempotency key `codex-mcp-acceptance-20260420-eric-1`; replay returned `idempotent_replay: true`
- a long-lived MCP client must reconnect after `user-env update` to refresh its advertised tool schema and loaded server code

## Acceptance Criteria

- a live MCP client can read runtime health and latest runtime report state
- a live MCP client can list workspaces and inspect at least one workspace status
- a live MCP client can perform bounded corpus search and semantic-readiness diagnostics
- listener lifecycle tools can register, inspect, list deliveries, and clean up a listener without leaving obvious residue
- any external write is either skipped deliberately or sent only to Eric with a clear test message
- results are recorded in the runbook and the plan is closed if no implementation blocker remains

## Closeout Notes

- `pcg` and `soylei` message search readiness passed with complete baseline message embeddings and no pending derived-text jobs.
- `default` message search readiness passed, but still has pending derived-text extraction jobs; this is not an MCP transport blocker.
- `pcg` and `soylei` `workspace.status` still show unhealthy summary rows when zero-message IM/MPIM rows are treated strictly; live validation suppresses stale mirror evidence separately and still passes. This remains a UX/status-policy refinement, not an MCP transport blocker.
- Managed semantic profiles advertise correctly through MCP. The `baseline` profile is ready; `local-bge` and `local-bge-rerank` remain unavailable in the managed venv until optional local-semantic dependencies and rollout are installed.

## Validation Plan

- live MCP tool calls from the connected MCP client
- `uv run python -m unittest tests.test_mcp_server -v`
- `uv run slack-mirror release check --require-managed-runtime --json`
- planning audit:
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
