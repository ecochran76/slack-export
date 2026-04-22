# 0096 | Slack report convergence design note

State: OPEN

Roadmap: P12

## Current State

Slack Mirror now has a strong report/export baseline:

- corpus search results expose stable `action_target` metadata
- selected search results can become bounded context packs
- selected search results can be persisted as managed `selected-results` export
  bundles
- browser users can select individual or visible-page search results and create
  selected-result reports
- channel/day exports remain a mature canonical export path
- managed export bundles provide deterministic IDs, manifests, stable
  `/exports/<export-id>` URLs, attachment download URLs, preview URLs, and
  lifecycle operations
- HTML reports already provide polished Slack-native presentation, including
  avatars, grouped messages, timestamps, thread styling, attachment metadata,
  image previews, and copy/print affordances
- DOCX and PDF renderers already layer over canonical export JSON for
  channel/day workflows

`../imcli` is converging from the other direction. It now has selected-result
report creation over CLI/API/MCP for Google Messages and WhatsApp, context
windows by count or time span, managed report artifacts, hideable technical
IDs, account-owner labels, attachment links, and initial portable query
operators.

The next convergence step is not to move Slack code into `imcli` or extract a
shared package immediately. It is to make Slack Mirror's report/export artifacts
explicitly mappable to a provider-neutral communication-event contract.

## Purpose

Record how Slack Mirror should participate in cross-corpus reporting
convergence while preserving the parts of Slack Mirror that are already better
than the sibling projects.

This is the Slack-side companion to the `imcli` report convergence note. A
future Ragmail note should separately cover mail-specific requirements.

## Best Slack Aspects To Preserve

Slack Mirror should remain the reference implementation for:

- managed export bundles
- deterministic export IDs
- API-served bundle manifests
- stable browser-visible `/exports/<export-id>` routes
- attachment download and preview URL contracts
- image thumbnails and preview behavior
- report/export lifecycle management
- browser search-to-report selection UX
- channel/day canonical exports
- DOCX/PDF rendering layered over canonical JSON
- Slack thread-aware rendering
- grouped same-sender message presentation
- Slack file, canvas, and email-preview repair/localization behavior

These are product strengths. Convergence should not flatten them into a weaker
lowest-common-denominator artifact.

## Best `imcli` Aspects To Adopt

Slack Mirror should align with these `imcli` convergence choices:

- selected search hits as report anchors, not only channel/day scopes
- context expansion by before/after count and before/after time span
- a durable action-target handoff object for agent/API/MCP workflows
- portable query operators with capability metadata
- human-readable reports with hideable technical identifiers
- an explicit account-owner or workspace-owner display concept rather than
  assuming a single universal "me"
- provider-neutral report/event names alongside Slack-native IDs

Slack already has much of the selected-result workflow. The remaining work is
mostly schema discipline and portable query/operator mapping.

## Communication-Event Contract Direction

The shared report abstraction should be a communication-event timeline, not a
chat-message-only schema.

Slack Mirror should be able to map local artifacts into neutral concepts such
as:

- `ReportSource`: workspace/account/source identity
- `ReportConversation`: channel, DM, MPIM, or other Slack conversation
- `ReportThread`: Slack root message timestamp plus replies
- `ReportParticipant`: Slack user, bot, app, deleted user, or unknown sender
- `ReportEvent`: message, reply, file share, edit, delete/tombstone, reaction,
  system event, canvas/file-derived-text hit, or email-preview-derived event
- `ReportAttachment`: Slack file, canvas, hosted file, localized file, email
  preview asset, or derived text source
- `ReportActionTarget`: selected search hit, derived-text hit, file-backed hit,
  or report/export candidate
- `ReportArtifactManifest`: bundle metadata, source refs, artifact URLs,
  preview URLs, renderer metadata, and counts

Slack-native details should remain under explicit source/native metadata:

- workspace ID and slug
- channel ID and channel type
- Slack message timestamp
- Slack thread timestamp
- Slack user ID or bot/app ID
- Slack file ID
- canvas/file derived-text source IDs
- permalink and private download URL evidence where available

## Query Convergence Requirements

Slack Mirror should continue its portable-query work with a shared
communications contract in mind.

Slack-compatible portable operators should include or map to:

- boolean terms, quoted phrases, grouping, and negation
- `before:`
- `after:`
- `since:`
- `until:`
- `on:`
- `from:`
- `to:` where Slack conversation membership or direct-message scope makes this
  meaningful
- `participant:`
- `workspace:`
- `channel:`
- `thread:`
- `has:attachment`
- `attachment-type:`
- `filename:`
- `mime:`
- `extension:`
- `sort:`
- `limit:`
- `context-before:`
- `context-after:`
- `slack.*` native extension operators

Unsupported or lossy operators should be surfaced through capability metadata
instead of silently ignored. For example, email-style `cc:` and `bcc:` are not
Slack-native concepts, but future shared clients should be able to learn that
from Slack's capability response.

## Email Requirements Slack Should Not Block

Slack does not need to implement email semantics, but Slack's contract choices
should not make them impossible.

Avoid names and assumptions that would prevent future Ragmail reports from
preserving:

- email subjects and normalized subjects
- `Message-ID`, `In-Reply-To`, and `References`
- `To`, `Cc`, `Bcc`, and `Reply-To` participant roles
- mailbox owner identity
- sent, received, archived, and indexed timestamp distinctions
- quoted-text and signature handling
- inline content-ID images
- HTML/plaintext alternatives
- forwarded-message blocks
- mailing-list metadata
- calendar invite attachments
- raw RFC822 or source-object hashes
- redaction hooks

This is the main reason the shared unit should be `ReportEvent` or
`CommunicationEvent`, not `SlackMessage` or `ChatMessage`.

## Slack-Specific Design Implications

Before shared-library extraction, Slack Mirror should:

- document how `selected-results.json` maps to a neutral report/event JSON
  draft
- keep Slack-native IDs available under source/native refs while adding neutral
  field names where useful
- keep managed export bundle behavior stable while adding neutral manifest
  fields
- keep `/exports/<export-id>` and preview URLs as the reference bundle-serving
  pattern
- expose selected-result action targets consistently through CLI/API/MCP/browser
  surfaces
- preserve channel/day exports, but treat selected-result reports as the first
  convergence gate with `../imcli`
- make context-window behavior explicit enough to compare with `imcli` before
  extracting `comm-context-window`
- avoid moving Socket Mode, Slack app setup, token handling, file/canvas repair,
  live sync, or Slack canonical DB migrations into shared libraries

## Implementation Follow-up

The first implementation slice added a top-level `events` projection to
managed `selected-results` artifacts. This projection maps resolved Slack
message context rows, selected and neighboring derived-text chunks, and linked
messages into provider-neutral event records while retaining Slack-native source
refs and the existing `context_pack` artifact for backwards compatibility.

## Shared-Library Gate

Do not extract shared code from this note alone.

The first gate opens when `slack-export` and `../imcli` can both emit or
losslessly map to compatible provider-neutral selected-result report artifacts.

For Slack Mirror, that means:

- selected-result exports have stable action targets
- context packs map to neutral before/hit/after event windows
- Slack report artifacts expose or map to neutral event, participant,
  conversation, thread, attachment, and manifest fields
- attachment URLs and previews remain service-owned and stable
- portable query operators and unsupported-operator behavior are documented
- the mapping preserves Slack-specific thread, file, canvas, user, bot, app,
  and permalink semantics

The shared code home should remain a separate sibling repo, likely
`../comm-corpus` or `../communications-core`, not `slack-export`,
`../imcli`, or `../ragmail`.

## Non-goals

- Do not merge Slack Mirror into `imcli`.
- Do not make Slack reports look like fake SMS or WhatsApp transcripts.
- Do not make channel/day exports disappear in favor of selected-result exports.
- Do not extract renderer code until at least two repos render from compatible
  neutral JSON.
- Do not share Slack runtime, auth, sync, Socket Mode, file repair, or DB
  migration code.
- Do not block email convergence by naming shared concepts after Slack-only
  primitives.

## Acceptance Criteria

- Slack Mirror has a repo-local note describing how its report/export work
  should converge with `imcli` while preserving Slack-specific strengths.
- The note states that Slack should map to a communication-event report model,
  not a chat-message-only schema.
- The note records the Slack artifact and bundle behavior that should become
  the reference for future shared bundle contracts.
- The note records email requirements that Slack schema choices should not
  block.
- `ROADMAP.md` and `RUNBOOK.md` wire this note into the P12 planning surface.

## Definition Of Done

- This note is preserved in repo-local planning docs.
- Follow-up implementation slices refer to this note when changing selected
  result exports, query operators, report schemas, or bundle manifests.
- A separate Ragmail note is written before mail-report convergence changes are
  implemented there.
