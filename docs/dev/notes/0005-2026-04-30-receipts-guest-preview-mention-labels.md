# 0005 | Receipts guest preview mention labels

Date: 2026-04-30
From: `../receipts`
Audience: Slack Export / Slack Mirror maintainers

## Context

Receipts validated a real Reports Guest Bundle flow using one live Slack result
and one live IM result. The parent grant now stores a display-only
`preview` block on each result target and renders those fields on `/g/{token}`
without calling child services.

The Slack result target preview was useful overall:

- title: `Slack message in joso-pcg`
- location: `pcg / #joso-pcg / joso-pcg`
- participant: a human sender label
- timestamp: `2026-03-30 02:38`

The remaining Slack-specific issue is that the preview snippet can still
include generic mention placeholders such as `@Slack user`.

## Request

Please make Slack selected-result summaries expose guest-safe rendered text for
mentions where policy allows display-name rendering.

Preferred behavior:

- Receipts-facing selected-result summaries should have a snippet/text preview
  where Slack user mentions are rendered as stable human-facing labels.
- Raw Slack ids should remain available through native ids, provenance, or
  extensions for audit/debugging, but not as the only guest-facing identity
  label.
- If a mention cannot be safely resolved or shown, Slack Export should make
  that explicit with a deterministic safe placeholder rather than a generic
  `@Slack user` string that hides whether the lookup failed or was redacted.

## Acceptance Target

A Receipts guest grant created from a Slack selected result should render a
guest preview row whose snippet uses guest-safe display labels for mentions,
while preserving child-owned privacy and identity policy in Slack Export.

Suggested validation:

- selected-result search/export fixture with a Slack mention
- API selected-result summary or export manifest shows the rendered preview
- Receipts guest preview created from that result no longer shows avoidable
  `@Slack user` placeholders

## Boundary

Receipts should not guess Slack identities or perform Slack-native mention
resolution. Slack Export owns Slack identity resolution, privacy policy, and
the distinction between unresolved and intentionally redacted mentions.
