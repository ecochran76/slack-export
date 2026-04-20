# MCP Retrieval Profile Search

State: CLOSED
Roadmap: P10
Opened: 2026-04-20
Closed: 2026-04-20

## Scope

Expose named retrieval-profile selection through MCP corpus search so agent clients can use the same profile contract reported by semantic readiness.

This slice covers:

- shared service request plumbing for an optional retrieval profile on corpus search
- MCP `search.corpus` schema and argument handling for retrieval profiles
- API/CLI parity checks where the shared request contract already supports profiles
- docs updates for the agent-facing search contract
- smoke validation against the release `baseline` profile

This slice does not include:

- installing optional BGE dependencies in the managed environment
- running broad `local-bge` backfills
- changing the release default profile away from `baseline`
- tuning ranking quality or benchmark thresholds

## Current State

- `search.profiles` and `search.semantic_readiness` expose `baseline`, `local-bge`, and `local-bge-rerank` through MCP.
- CLI corpus search already documents `--retrieval-profile baseline`.
- MCP `search.corpus` accepts low-level knobs such as `mode`, `fusion`, `model`, and `rerank`, but does not expose retrieval-profile selection.
- The post-restart semantic MCP smoke in `0073` confirmed direct `model=BAAI/bge-m3` corpus search fails under the current local-hash provider, so agent clients need profile-level selection rather than ad hoc model overrides.
- The implementation now adds `retrieval_profile` to MCP and API corpus search and resolves profiles inside the shared app service before dispatching to the existing corpus-search implementation.
- Local repo MCP smoke confirms:
  - `tools/list` exposes `retrieval_profile` on `search.corpus`
  - `retrieval_profile=baseline` returns corpus results
  - an unknown profile returns a structured MCP `INVALID_REQUEST` error
- The currently connected installed MCP server must be refreshed with `user-env update` before long-lived clients see the new argument.

## Acceptance Criteria

- MCP `search.corpus` accepts an optional `retrieval_profile` argument: met.
- `retrieval_profile=baseline` works through local repo MCP corpus search without changing the release default: met.
- invalid profile names return a structured MCP error rather than silently falling back: met.
- profile selection remains thin over shared application logic: met.
- docs and planning files describe the new MCP-facing contract: met.

## Validation Plan

- targeted unit tests for MCP search profile arguments
- connected MCP smoke:
  - `search.corpus` with `retrieval_profile=baseline`
  - invalid retrieval profile error path if feasible without leaking private data
- `uv run python -m unittest tests.test_mcp_server -v`
- `uv run slack-mirror release check --require-managed-runtime --json`
- planning audit:
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`

## Implementation Notes

- `SlackMirrorAppService.corpus_search` and `corpus_search_page` now accept `retrieval_profile_name`.
- When a profile is supplied, the service resolves the profile, applies its provider/model/weights/rerank settings, and then calls the existing corpus-search implementation.
- MCP `search.corpus` exposes `retrieval_profile` and forwards it to the shared service.
- API corpus routes accept `retrieval_profile` on both workspace-scoped and all-workspace routes.
- `README.md` and `docs/API_MCP_CONTRACT.md` document the agent-facing profile selector.
