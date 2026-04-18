# Operator Frontend Reuse Architecture

State: OPEN
Roadmap: P09
Opened: 2026-04-18
Follows:
- `docs/dev/plans/0050-2026-04-15-tenant-onboarding-wizard-and-settings.md`

## Scope

Define the frontend architecture that should replace the current inline Python-rendered tenant-management page while maximizing reuse across:

- `slack-export`
- `../imcli`
- `../ragmail`

This plan covers:

- choosing the frontend-app architecture for the operator console
- defining the shared-vs-repo-local boundary for reusable frontend code
- establishing the theming and component-token contract so visual redesigns can happen without rewriting behavior
- decomposing the frontend migration into subprojects that can each be sliced cleanly
- identifying the first migration slice for `/settings/tenants`

This plan does not include:

- rewriting all browser surfaces in one slice
- replacing the existing Python auth or JSON API contracts
- forcing `../imcli` or `../ragmail` into one repo or one release train
- shipping a cross-repo package publish pipeline in the first slice
- selecting Astro as the primary operator-console architecture

## Current State

- `slack-export` now has several authenticated browser surfaces, but they are still assembled as inline HTML/CSS/JS strings in `slack_mirror/service/api.py`
- the current `/settings/tenants` page is functionally rich, but visual inspection shows that it has become too dense and too custom to iterate on cleanly:
  - giant tenant cards
  - redundant status blocks
  - weak separation between primary actions and low-frequency setup actions
  - no reusable frontend widget layer
- the user confirmed that frontend theming compatibility is required so the information architecture can remain stable while look-and-feel evolves independently
- the user also confirmed that `slack-export`, `../imcli`, and `../ragmail` are sibling operator products with essentially the same platform purpose over different communication domains:
  - Slack
  - SMS / WhatsApp / messaging
  - Email
- all three repos are likely to need the same class of frontend building blocks:
  - authenticated operator shell
  - status badges and pills
  - metric strips
  - dense row or table views
  - action menus
  - logs and runtime state surfaces
  - search or result primitives
  - report-generation and artifact workflows
  - selection and bulk-action affordances

## Decision

The preferred direction is:

- `Vite`
- `React`
- `TypeScript`
- a reusable shared operator UI layer

Astro is not the preferred primary architecture for this operator console because the target surface is application-like rather than content-first or island-light.

## Target Architecture

### Shared frontend layers

Design the reusable frontend around three layers:

1. `operator-types`
   - neutral UI-facing types for status, metrics, actions, and row descriptors
2. `operator-theme`
   - tokens and theme contract for color, spacing, radii, typography, shadows, motion
3. `operator-ui`
   - reusable presentational and stateful widgets built on those types and tokens

The shared layer should be communication-domain-neutral. It should not assume Slack-specific naming.

### Repo-local adapter layer

Each repo should own:

- its API client
- auth integration
- domain mapping from repo-local backend data into shared operator UI types
- any transport-specific widgets that truly cannot be generalized

For `slack-export`, the first repo-local adapter target is the tenant-management surface.

### Theming contract

Theme architecture must be first-class from the beginning:

- semantic status variants like `success`, `warning`, `danger`, `info`, `neutral`
- CSS variables or equivalent token plumbing for colors, density, spacing, and type
- no hardcoded Slack-specific visual language in shared widgets
- presentational components consume semantic variants and tokens, not business-specific conditionals

This is required so visual redesigns can happen later without changing behavior or data flow.

## Proposed Frontend Package Shape

This slice does not require immediate extraction into a separate monorepo package, but the architecture should be designed so extraction is easy.

Initial in-repo target shape:

```text
frontend/
  app/
  src/
    theme/
    components/
    features/
    lib/
```

Target reusable shape after the first proving slice:

```text
packages/
  operator-types/
  operator-theme/
  operator-ui/
apps/
  slack-operator/
  imcli-operator/
  ragmail-operator/
```

The first slice can keep all of this inside `slack-export` if that reduces coordination cost, but it should preserve the package boundary concept from day one.

## Subprojects

The operator frontend should be broken into these reusable subprojects so implementation can proceed in bounded slices instead of one broad rewrite:

1. Shell and navigation
   - app shell
   - top bar
   - account/avatar chip
   - collapsible side rail
   - global context selectors
   - route framing and responsive layout behavior
2. Theme and design system
   - token contract
   - density modes
   - semantic status colors
   - typography and spacing scales
   - motion rules
   - theme swapping without behavioral churn
3. Entity-management workbench
   - dense row/table views
   - metric strips
   - primary and maintenance actions
   - expandable details
   - row-local status and feedback
4. Search workbench
   - advanced query controls
   - saved views
   - grouping and facet patterns
   - selection model
   - candidate staging and bulk actions
5. Report and artifact pipeline
   - report generation
   - export workflows
   - result-to-report handoff
   - artifact history and lifecycle operations
6. Logs and runtime observability
   - bounded recent logs
   - poll-first live refresh
   - runtime and queue-state summaries
   - service and worker visibility
7. Repo-local adapters
   - thin API clients
   - auth integration
   - mapping from repo-local data into shared operator contracts
   - transport-specific widgets only where generalization would be forced

## Planned Slice Order

The intended implementation order is:

1. keep this architecture plan as the parent planning slice
2. open a shell/theme child slice for the shared app-shell contract
3. open a tenant-workbench child slice for `/settings/tenants`
4. open a search-workbench child slice for advanced controls plus selection and bulk actions
5. open a report/artifact child slice for generation and result-manipulation workflows
6. open a logs/runtime child slice for observability refinement

Each child slice should stay bounded and should prove the shared package-boundary assumptions instead of widening this parent plan indefinitely.

## First Migration Slice

The first implementation slice should:

- scaffold the frontend app in this repo
- preserve the existing Python API and auth contracts
- serve built assets from the existing Python service
- rebuild `/settings/tenants` first as the proving surface
- leave the legacy page available until the replacement reaches parity

The replacement `/settings/tenants` should emphasize:

- dense row-based tenant list instead of large nested cards
- one top-level runtime state per tenant
- compact metric strip
- primary action plus overflow or maintenance actions
- expandable details for setup and low-frequency actions

## Reusable Widget Targets

The shared widget library should at minimum support:

- `OperatorShell`
- `StatusBadge`
- `MetricPill`
- `MetricStrip`
- `EntityRow`
- `ExpandableSection`
- `ActionMenu`
- `InlineFeedback`
- `LogsPanel`
- `DetailPanel`

The semantic model should be neutral:

- `RuntimeStatus`
- `SyncStatus`
- `IngestStatus`
- `ManagedEntity`
- `ActionDescriptor`
- `MetricDescriptor`

Avoid Slack-shaped naming in the shared contract.

## Acceptance Criteria

- roadmap and bounded plan text clearly record that the frontend direction is reusable across `slack-export`, `../imcli`, and `../ragmail`
- the chosen architecture is explicitly `Vite + React + TypeScript`, not further inline-page expansion
- the shared-vs-local boundary is documented clearly enough that implementation can begin without reopening broad architecture debate
- theming compatibility is a first-class contract, not a later cleanup item
- the roadmap now decomposes the operator frontend into explicit reusable subprojects and an intended slice order
- the first migration slice is clearly scoped to `/settings/tenants`

## Validation Plan

- planning audit:
  - `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
- roadmap / plan / runbook wiring review:
  - ensure `P09` references this plan
  - ensure the runbook records the architecture decision and why it was opened
