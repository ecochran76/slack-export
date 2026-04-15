# Frontend Search Surface And Hardening

State: CLOSED
Roadmap: P06
Opened: 2026-04-14
Follows:
- `docs/dev/plans/0006-2026-04-11-search-evaluation-modernization.md`
- `docs/dev/plans/0039-2026-04-14-frontend-row-state-chips.md`

## Scope

Introduce a first-class authenticated browser search surface over the already-shipped search API and harden the frontend patterns needed for that surface to hold up under real operator use.

This plan is specifically about:

- adding a browser search page instead of leaving search API-only
- keeping the browser surface thin over the existing shared search service and API contracts
- hardening browser-side query, loading, error, and result-state behavior for larger result sets and cross-workspace use

This plan is not a generic reopening of the closed service-surface or search-modernization lanes.

## Current State

- authenticated browser surfaces already exist for:
  - `/`
  - `/settings`
  - `/runtime/reports`
  - `/exports`
- the first browser search slice is now shipped at `/search`, with:
  - authenticated browser access
  - landing-page navigation
  - URL-backed search state
  - workspace vs all-workspace scope
  - mode, limit, derived-text kind, and source-kind controls
  - bounded pagination with `offset` plus total-result counts
  - thin browser fetches over the existing corpus-search and readiness APIs
  - workspace-readiness context
  - in-page result cards with stable operator metadata and bounded refinement links
  - stable JSON detail destinations for message and derived-text hits, backed by repo-owned API routes instead of a second browser viewer
  - shared low-level browser helper extraction for HTML escaping, busy-label handling, and inline-manager actions reused across `/runtime/reports`, `/exports`, and `/search`
  - shared browser-side fetch/error helpers reused across `/runtime/reports`, `/exports`, and `/search` for bounded request plumbing without introducing a larger page framework
  - shared authenticated topbar rendering across `/`, `/settings`, and `/search`, so the main browser entry surfaces no longer hand-roll separate navigation chrome
- the managed live install has been refreshed from the current repo through `user-env update`, and post-redeploy browser QA passed on:
  - `/`
  - `/settings`
  - `/search`
  - `/runtime/reports`
  - `/exports`
- browser auth, same-origin write discipline, and basic inline-manager hardening are already shipped
- the shared search service and HTTP API already expose:
  - `GET /v1/workspaces/{workspace}/search/corpus`
  - `GET /v1/search/corpus`
  - `GET /v1/workspaces/{workspace}/search/readiness`
  - `GET /v1/workspaces/{workspace}/search/health`
  - `GET /v1/workspaces/{workspace}/messages/{channel_id}/{ts}`
  - `GET /v1/workspaces/{workspace}/derived-text/{source_kind}/{source_id}?kind=...`
- corpus search already supports:
  - workspace-scoped or all-workspace search
  - `lexical`, `semantic`, and `hybrid` modes
  - result limits
  - derived-text kind filtering
  - derived-text source-kind filtering
- browser users currently have no first-class way to:
  - run corpus search from the frontend
  - inspect readiness from the same browser workflow
  - distinguish workspace-scoped vs all-workspace search without hand-calling JSON routes
- the current frontend remains largely inline HTML/CSS/JS in `slack_mirror/service/api.py`, so any new surface should prefer shared helpers and bounded rendering patterns instead of another one-off blob

## Deferred Follow-Ups

### Track A | Browser Search Baseline

- decide whether the search form ever needs additional bounded filters before reopening this area

### Track B | Search Result Presentation

- render message and derived-text hits distinctly without inventing a second search contract
- show the minimum operator-useful metadata per hit:
  - workspace
  - channel or source label when available
  - result kind
  - snippet/text preview
  - retrieval mode/score hints where useful
- provide stable links back to existing repo-owned surfaces when available instead of embedding large secondary viewers into the search page
- current shipped baseline:
  - message vs derived-text result cards
  - workspace, result kind, source-kind, derivation-kind, timestamp, and retrieval-mode hints
  - row-level operator metadata such as:
    - channel
    - user
    - thread marker
    - source id
    - extractor
    - local path
  - bounded refinement links for:
    - workspace scope
    - channel scope for message hits
    - thread-context narrowing for threaded message hits
    - same-kind and same-source-kind narrowing for derived-text hits
  - stable repo-owned JSON destinations from result cards for:
    - message detail
    - derived-text detail plus chunk payload
- deferred:
  - decide whether the repo needs any browser-native viewer beyond the current refinement and JSON destination links before adding more UI chrome

### Track C | Frontend Hardening For Search

- shipped:
  - empty, loading, and request-failure states
  - duplicate-submit protection while a search is in flight
  - URL query-string state so current searches are reloadable and shareable
  - local validation for missing query or missing workspace in workspace scope
  - bounded previous/next pagination backed by API `offset`
  - explicit total-result counts from the API so the browser can show page position and result range
- the lowest-risk shared helper extraction is now landed; any follow-on extraction should justify itself beyond the already-shared browser primitives
- the current bounded pagination contract is sufficient for the shipped browser surface; defer infinite scroll or cursor pagination unless the API contract changes again

### Track D | Readiness And Operator Context

- shipped:
  - inline workspace readiness panel on `/search` for one-workspace searches
- deferred:
  - decide whether readiness should stay inline, collapse by default, or move to a drill-down affordance after real operator use
- keep search-health benchmark execution off the hot search form path unless a narrow follow-up proves browser-triggered health checks are worth the UI complexity

### Track E | Follow-On Frontend Hardening

- factor any repeated browser-side fetch/state helpers that the new search page shares with `/runtime/reports` or `/exports`
- the bounded shared request/error helper extraction is now shipped for:
  - runtime-report create
  - export workspace/channel loading
  - export create
  - search execution
  - readiness loading
- shared authenticated topbar rendering is now shipped for `/`, `/settings`, and `/search`
- any future frontend-hardening follow-up should cover:
  - browser pagination for large report/export lists
  - further extraction of inline browser helpers inside `slack_mirror/service/api.py`

## Non-Goals

- replacing the existing search APIs with browser-only logic
- building a SPA, bundler, or frontend framework migration
- reopening search ranking-model, extraction-provider, or backend-storage planning
- adding browser-side benchmark authoring or a full search-admin console
- inventing a second canonical viewer for exports, attachments, or runtime reports inside `/search`

## Acceptance Criteria

- the repo has one explicit open plan for browser search introduction and related frontend hardening
- the plan keeps browser search thin over the shipped shared search service and API contracts
- the required browser scope, filters, result presentation, and state-hardening work are explicit enough to execute in bounded child slices
- readiness exposure is planned deliberately instead of being left as an afterthought
- follow-on frontend maintainability work is identified without reopening the entire frontend lane

## Closure

- `P06` is closed as shipped.
- The browser search surface is live in the managed install and has been validated through real browser login plus page-level QA.
- Any later work in this area should open as a new bounded slice instead of extending this plan indefinitely.

## Validation

- `python scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
- `git status --short`
