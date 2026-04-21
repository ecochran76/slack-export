# 0083 | Cross-corpus export convergence

State: OPEN

Roadmap: P12

## Current State

Slack Mirror has the most mature export/report stack among the sibling local
communication projects:

- managed export bundles with deterministic export IDs
- manifest-backed `/exports/<export-id>` publishing
- attachment download and preview URLs
- channel/day JSON as the canonical export artifact
- HTML chat-style rendering with avatars, grouped bubbles, timestamps,
  thread styling, compact identifiers, attachment metadata, image thumbnails,
  and lightbox behavior
- DOCX/PDF renderers layered on the same JSON artifact
- API routes for export listing, detail, create, rename, delete, bundle file
  serving, and preview serving
- browser search and export-management surfaces
- corpus search result `action_target` metadata for message and derived-text
  hits
- no explicit shared query grammar contract yet for portable filters such as
  boolean expressions, time filters, actor filters, channel/thread filters, or
  attachment filters

Adjacent projects are converging on the same product class:

- `../imcli` owns Google Messages and WhatsApp local mirroring/search and is
  planning selected-result chat exports with configurable before/after context
  windows
- `../ragmail` owns mail corpora and already has search, thread rendering,
  attachment extraction, case bundles, report manifests, and CLI/HTTP/MCP
  evidence workflows

The shared product direction is one local communications search/export/report
experience. The safe engineering path is not an immediate codebase merge. It is
to keep provider runtimes independent while aligning shared contracts and later
extracting small libraries only after multiple repos prove the same shape.

## Problem Statement

Slack Mirror, `imcli`, and Ragmail are at risk of independently rebuilding the
same upper-layer features:

- query parsing and portable operator semantics
- selected search result handoff
- before/after context expansion
- export bundle manifests
- attachment links and previews
- report rendering
- browser export managers
- future React/Vite operator workbenches

Directly folding all three projects into one massive service now would also be
risky:

- Slack, instant messaging, and email have materially different runtime,
  authentication, sync, threading, attachment, and provider-fidelity semantics
- a premature mega-merge would likely create a larger monolith rather than real
  reuse
- shared abstractions would be guessed before two repos prove compatible
  artifacts

## Goal

Guide Slack Mirror development toward a unified communications service direction
without merging runtimes prematurely.

The near-term goal is to make Slack Mirror's selected-result export/report layer
compatible with the provider-neutral contract that `../imcli` is starting to
plan.

That includes the search side of the contract: Slack Mirror should be able to
accept, emit, or losslessly map enough shared query/action-target semantics that
portable filters select comparable Slack records.

The medium-term goal is to unlock a separate shared-library repo when at least
two projects can consume the same contracts.

## Recommended Direction

Keep the projects independent for now.

Converge in this order:

1. independent products
2. compatible provider-neutral export/report artifacts
3. shared contracts in a separate sibling repo
4. shared bundle/report/context helpers
5. shared React/Vite operator workbench components
6. possible common control plane only after the contracts are stable

Do not target one massive service as the next milestone.

## Shared Library Gate

Shared-library development should begin only when at least two repos have
compatible implementations or lossless mappings for the same provider-neutral
workflow.

The first expected gate is selected-result export/reporting across:

- `slack-export`
- `../imcli`

This gate should include compatible search action targets and enough shared
query semantics that common portable operators select comparable records before
report/export rendering begins.

`../ragmail` should be the third proving implementation before deeper frontend
or common-control-plane commitments.

Do not extract shared libraries for:

- Slack Socket Mode
- Slack tenant onboarding
- Google browser/runtime ownership
- WhatsApp adapter behavior
- email PST/MBOX/EML/MIME ingest
- provider-specific auth/session/keyring behavior
- canonical database migrations
- one universal search engine
- forcing every provider to support every portable operator immediately

## Shared Library Home

The shared libraries should not live inside `slack-export`, `../imcli`, or
`../ragmail` as the long-term source of truth.

Create a separate sibling repo when the first extraction gate is met:

```text
../comm-corpus
```

Acceptable alternative:

```text
../communications-core
```

Reason:

- Slack Mirror, `imcli`, and Ragmail should be equal consumers
- the shared packages should not inherit Slack-only or instant-message-only
  assumptions
- versioning and compatibility become explicit
- extraction can proceed package by package instead of forcing a monorepo or
  mega-service rewrite

## Candidate Shared Packages

### 1. `comm-export-contracts`

First candidate.

Owns:

- action targets
- source refs
- conversation refs
- thread refs
- message refs
- attachment refs
- context windows
- report payload schemas
- export artifact schemas
- manifest schemas
- attachment link schemas

### 2. `comm-bundle-store`

Owns:

- deterministic export ID generation
- safe export path handling
- manifest listing
- manifest writing
- rename/delete helpers
- URL building
- preview URL metadata

Slack Mirror already has much of this in `slack_mirror.exports`; extract only
after `imcli` has implemented a compatible bundle shape.

### 3. `comm-report-renderer`

Owns:

- provider-neutral report JSON to HTML rendering
- message bubble rendering
- grouped same-sender rendering
- avatar/initial fallback
- compact ID metadata
- reaction rendering
- attachment rows
- preview/download link rendering

Delay extraction until Slack Mirror and `imcli` both render from compatible
neutral JSON.

### 4. `comm-context-window`

Owns storage-agnostic context policy:

- before/after by message count
- before/after by time span
- duplicate context merge
- exact-hit marker placement
- thread inclusion policy
- conversation boundary enforcement

Each backend provides its own neighbor/context provider.

### Query contract note: `comm-search-contracts`

Owns query and result contracts, not engines:

- query grammar and AST types
- boolean terms, phrases, grouping, and negation
- temporal operators such as `before:`, `after:`, `since:`, `until:`, and
  `on:`
- actor operators such as `from:`, `to:`, `participant:`, `account:`, and
  `me:`
- source/conversation operators such as `source:`, `platform:`, `tenant:`,
  `workspace:`, `channel:`, and `thread:`
- attachment/file operators such as `has:attachment`, `attachment-type:`,
  `filename:`, `mime:`, and `extension:`
- result-shaping options such as `sort:`, `limit:`, `context-before:`, and
  `context-after:`
- provider-native extension namespaces such as `slack.*`, `mail.*`,
  `whatsapp.*`, and `google_messages.*`
- operator capability metadata
- search request fields
- search result fields
- score and explain metadata
- pagination
- readiness
- action targets
- derived-text result shape

Delay extracting a shared parser until Slack Mirror and at least one sibling
repo prove compatible local grammar behavior.

### 6. `comm-workbench-ui`

Later candidate.

Owns React/Vite UI primitives for:

- source/tenant selector
- search workbench
- result selection
- context-window controls
- export manager
- artifact history
- attachment preview components
- operator status cards

Do not extract this before CLI/API/MCP export contracts are stable.

## Slack Mirror Development Goals

### G1. Add selected-result export inputs

Current channel/day exports are useful, but the convergence target is:

```text
selected search hits -> context expansion -> report bundle
```

Slack Mirror should add export inputs that consume `action_target` values from
search results.

Context controls should include:

- before message count
- after message count
- before time span
- after time span
- thread inclusion policy
- attachment inclusion policy
- duplicate context merge policy

### G2. Add provider-neutral report JSON

Keep `channel-day.json` for compatibility, but add or map to a neutral report
artifact with fields such as:

- source
- conversation
- thread
- participants
- messages
- exact-hit markers
- reactions
- attachments
- source/native IDs

Slack-native identifiers should remain available under explicit native/source
metadata.

### G3. Document Slack-to-neutral mappings

Required mapping table:

- workspace -> source
- channel/DM/MPIM -> conversation
- thread timestamp -> thread
- Slack message timestamp -> message
- Slack user -> participant
- Slack file -> attachment
- Slack canvas -> attachment or derived source
- Slack email preview -> attachment or derived source

### G4. Preserve the managed bundle contract

Do not destabilize the proven bundle behavior:

- deterministic export ID
- `manifest.json`
- canonical JSON artifact
- `index.html`
- `/exports/<export-id>`
- `/exports/<export-id>/<filepath>`
- `/exports/<export-id>/<filepath>/preview`
- attachment `download_url`
- attachment `public_url`
- attachment `preview_url`

### G5. Keep Slack runtime service-owned

Do not move these into shared libraries:

- Socket Mode
- Slack app manifest generation
- tenant credential installation
- Slack file/canvas repair
- Slack outbound/listener semantics
- workspace live services

## Ragmail Unlock Goals

Ragmail should unlock participation by:

- aligning mail search operators with the shared portable grammar where email
  semantics permit it
- exposing mail search hits as stable action targets
- mapping rendered thread output to neutral report JSON
- preserving email-specific semantics:
  - mailbox
  - folder/label
  - MIME part
  - attachment occurrence
  - message-id
  - archive corpus
  - live source
  - dedupe/logical-message cluster
- emitting artifact manifests compatible with the shared bundle contract
- exposing attachment links or portable references compatible with shared
  renderer expectations

Ragmail should keep PST/MBOX/EML parsing, MIME extraction, live mailbox sync,
segmented ingest, and corpus registry mechanics service-owned.

## Non-Goals

- Do not merge `slack-export`, `../imcli`, and `../ragmail` in this slice.
- Do not create a shared database schema in this slice.
- Do not extract provider runtime/auth/sync libraries.
- Do not rewrite the frontend before CLI/API/MCP export contracts stabilize.
- Do not make `slack-export` the owner of shared libraries long term.
- Do not make `../imcli` the owner of shared libraries long term.

## Acceptance Criteria

- `ROADMAP.md` records the cross-corpus convergence direction.
- This plan records when shared-library development should begin.
- This plan records where shared libraries should live.
- This plan records Slack Mirror development goals required to unlock the first
  shared-library gate.
- This plan records Ragmail unlock goals.
- The direction preserves provider-specific runtime ownership.
- The next implementation slice is clear.

## Definition Of Done

This planning slice is done when:

- roadmap and runbook wiring are complete
- Slack Mirror's next export/report child plan can be opened without reopening
  the broad merge-vs-independence debate
- the shared-library extraction gate is explicit enough that future agents do
  not create speculative shared packages prematurely

## Recommended Next Child Plan

Open a bounded implementation plan for selected-result exports:

```text
0084-YYYY-MM-DD-selected-result-export-contract.md
```

Scope should include:

- consume `action_target` selections
- expand context by message count and time span
- emit provider-neutral report JSON
- preserve current channel/day export compatibility
- create managed bundle artifacts from the neutral report JSON
- expose create/list/get over CLI/API/MCP or API first, depending on the
  service seam with lowest churn

That child plan should not include React/Vite frontend migration yet.
