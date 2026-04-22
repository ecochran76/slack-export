# Frontend Contract Notes

This document records the first UI-facing contract boundary for the future
operator frontend. It complements:

- `docs/dev/plans/0051-2026-04-18-operator-frontend-reuse-architecture.md`
- `docs/dev/plans/0083-2026-04-21-cross-corpus-export-convergence.md`
- `docs/dev/plans/0096-2026-04-21-frontend-selected-result-contract-model.md`

## Selected Result Model

The selected-result UI model lives in:

```text
frontend/src/contracts/selectedResults.ts
```

The model is intentionally provider-neutral. Shared frontend code should talk
about sources, conversations, threads, participants, attachments, candidates,
targets, artifacts, and reports. Repo-local adapters map provider-specific API
fields into that shape.

## Slack To Neutral Mapping

| Slack Mirror field | Neutral frontend field |
| --- | --- |
| `workspace` / `workspace_id` | `SourceRef` |
| `channel_id` / `channel_name` | `ConversationRef` |
| `thread_ts` | `ThreadRef` |
| `ts` | `SelectedResultTarget.messageId` or `MessageContextItem.id` |
| `user_id` / `user_label` | `ParticipantRef` |
| `source_kind=file` / `source_id` | `AttachmentRef` |
| `action_target` | `SelectedResultTarget` |
| corpus result row | `SearchResultCandidate` |
| `context_policy` | `ContextPolicy` |
| `selected-results.json` | `SelectedResultReportArtifact` |

Provider-native identifiers should be preserved under `native` metadata instead
of becoming shared type names.

## Adapter Boundary

Shared or future shared code may own:

- result selection state
- visible-result bulk selection
- context-window controls
- managed artifact references
- selected-result report view actions
- status/type chips and print/copy affordances

Slack Mirror remains the owner of:

- API fetch paths
- auth/session handling
- Slack-specific route names and query parameters
- Slack native identifiers and fallback labels
- conversion from current API payloads into the neutral frontend contracts

## Status Widget Model

The first reusable status primitive lives in:

```text
frontend/src/contracts/status.ts
frontend/src/components/StatusWidget.tsx
```

The status model is intentionally small:

- tone: `neutral`, `success`, `warning`, `danger`, or `info`
- label: operator-facing short text
- summary/detail: optional explanatory copy for panel use

Shared frontend code may render badges and panels from that neutral shape.
Repo-local adapters must own provider-specific status translation, such as
mapping Slack Mirror API `ok` / `warn` / `bad` tones into neutral tones or
formatting Slack-specific next-action labels.

This boundary should also fit `../imcli` and `../ragmail`: those repos can map
SMS/WhatsApp account state or mailbox/source state into the same tone, label,
summary, and detail shape without adopting Slack terminology.

## Entity Table Model

The first reusable table primitive lives in:

```text
frontend/src/components/EntityTable.tsx
```

The table model owns only reusable presentation mechanics:

- ARIA-labelled scroll region
- column headers
- row-key resolution
- row-header cells
- body cell rendering

Repo-local adapters own the row data and column definitions. For Slack Mirror,
`TenantWorkbench` maps tenant status into columns such as readiness, DB stats,
backfill, live sync, health, semantic readiness, and details. `../imcli` and
`../ragmail` should be able to map account/chat or mailbox/source rows into
the same primitive without importing Slack-specific field names.

Do not add table sorting, filtering, selection, bulk actions, or persistence to
the primitive until the search and entity-management workbenches prove which
behaviors are shared across at least two repos.

## View Toggle Model

The first reusable view switch primitive lives in:

```text
frontend/src/components/ViewToggle.tsx
```

The primitive owns only the segmented button rendering for string-valued view
options:

- current value
- option labels and values
- `aria-pressed` state
- change callback

Repo-local workbenches own what each option means. For Slack Mirror, the
tenant workbench maps `cards` and `table` to the current status-card and
entity-table views. `../imcli` and `../ragmail` should be able to reuse the
same primitive for account/source, search-result, report, or log density
controls without importing Slack-specific terms.

Do not persist view preferences or add route synchronization to the primitive
until at least two workbenches prove the same behavior is needed.

## Detail Panel Model

The first reusable disclosure primitive lives in:

```text
frontend/src/components/DetailPanel.tsx
```

The primitive owns only neutral native-disclosure mechanics:

- title and optional summary metadata
- open/closed affordance styling
- card and compact visual variants
- child content placement

Repo-local workbenches own what the details mean. For Slack Mirror, the tenant
workbench uses `DetailPanel` for live-unit, text/embedding, and semantic
readiness diagnostics. `../imcli` and `../ragmail` should be able to reuse the
same primitive for account/source diagnostics, message/export provenance, or
report metadata without importing Slack-specific tenant terminology.

Do not add persisted expansion state, route synchronization, accordions, or
remote lazy-loading to the primitive until at least two workbenches prove the
same behavior is needed.

## Action Button Group Model

The first reusable action-affordance primitive lives in:

```text
frontend/src/components/ActionButtonGroup.tsx
```

The primitive owns only neutral grouped-action rendering:

- action label
- tone variant
- disabled state
- short explanatory reason text

Repo-local workbenches own what actions mean and when they are available. For
Slack Mirror, the tenant workbench derives a single recommended tenant action
from credential, config, activation, backfill, live-sync, and queue state. The
first enabled React mutations are deliberately narrow: `Install credentials`
posts non-empty Slack credential fields to the existing tenant credentials API
without echoing secrets; `Activate tenant` posts to the existing tenant
activate API and then starts the bounded initial-sync backfill; `Run initial
sync` posts to the existing tenant backfill API; and live-sync
start/restart/stop post to the existing tenant live API. `Restart live sync` is
enabled only as a recovery action when live units are active and status is
degraded. `Stop live sync` is enabled only when live units are active and
requires typed tenant-name confirmation. `Retire tenant` is exposed only for
non-protected tenants, requires typed tenant-name confirmation, and preserves
the explicit optional mirrored-DB deletion choice. Maintenance backfill remains
disabled until its mutation contract is migrated deliberately. `../imcli` and
`../ragmail` should be able to reuse the same primitive for account/source
actions, candidate/report actions, or runtime maintenance actions without
importing Slack-specific verbs.

Do not add optimistic updates, confirmation flows, or transport behavior to the
primitive until at least two workbenches prove the same behavior is needed.

## Tracked Mutation Model

The first local mutation-state helper lives in:

```text
frontend/src/lib/trackedMutation.ts
```

The helper owns only keyed busy, success, error, and after-settled bookkeeping:

- stable row/entity key
- busy message
- success message derived from the response
- error message derived from the thrown value
- optional after-settled callback, such as a status refresh

Repo-local workbenches still own transport, payloads, confirmation policy, and
operator-facing action semantics. For Slack Mirror, `TenantWorkbench` uses this
helper for initial sync and live-sync actions while keeping Slack-specific
routes and payloads local. `../imcli` and `../ragmail` should be able to map
account/source, search-result, report, or runtime-maintenance mutations into
the same keyed state mechanics without importing Slack-specific terms.

Do not add optimistic updates, retries, global stores, toast queues, or
transport-specific behavior to this helper until at least two workbenches prove
the same behavior is needed.

## Refresh Status Model

The first reusable polling/freshness primitive lives in:

```text
frontend/src/components/RefreshStatus.tsx
```

The primitive owns only neutral refresh-status rendering:

- last-updated label
- optional polling interval text
- loading, idle, and error display states
- manual refresh button affordance

Repo-local workbenches own the transport, polling policy, timestamps, and error
handling. For Slack Mirror, the tenant workbench continues to fetch
`/v1/tenants` and now passes the last successful refresh time plus manual
refresh callback into `RefreshStatus`. `../imcli` and `../ragmail` should be
able to reuse the same primitive for account/source freshness, search-result
refresh, report generation status, or runtime health polling without importing
Slack-specific route names.

Do not add streaming behavior, persisted intervals, background retry policy, or
transport behavior to the primitive until at least two workbenches prove the
same behavior is needed.

## Confirm Dialog Model

The first reusable confirmation primitive lives in:

```text
frontend/src/components/ConfirmDialog.tsx
```

The primitive owns only neutral confirmation UI mechanics:

- title, message, and optional details
- neutral or danger tone
- cancel and confirm actions
- optional typed confirmation text
- optional workbench-owned confirmation options

Repo-local workbenches own what action is being confirmed and what mutation
runs after confirmation. For Slack Mirror, the tenant workbench uses
`ConfirmDialog` to guard `Stop live sync` and `Retire tenant` with typed
tenant-name confirmation. Retirement also passes a workbench-owned mirrored-DB
deletion checkbox as neutral dialog content. `../imcli` and `../ragmail`
should be able to reuse the same primitive for destructive account/source,
report, or artifact actions without importing Slack-specific terms.

Do not add mutation transport, global dialog routing, or provider-specific
labels to the primitive until at least two workbenches prove the same behavior
is needed.

## Extraction Gate

Do not move these types into a sibling shared package until at least one sibling
repo, most likely `../imcli`, can map its selected-result workflow into the same
shape without lossy provider assumptions.
