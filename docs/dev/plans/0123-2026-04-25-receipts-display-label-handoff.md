# 0123 | Receipts display label handoff

State: CLOSED

Roadmap: P12

## Context

`../receipts` now renders Slack Mirror results through its shared workbench. The
shared frontend should show human-facing sender and channel names, not Slack
internal IDs. This is also the expected direction for WhatsApp, Google
Messages, and any future provider that stores stable internal identifiers
alongside user-facing labels.

Receipts added a defensive display normalizer on 2026-04-25:

- Slack-style `<@U...|label>` and `<#C...|label>` text is rendered as
  `@label` and `#label`.
- Common `:emoji:` shortcodes are rendered as Unicode emoji when known.
- ID-looking labels such as `U0AC4G11SH3` and `C0AHHG09TEU` are suppressed
  from the primary UI rather than shown as human names.

That parent-side normalization prevents ID leakage, but it cannot recover a
real sender name when Slack Mirror does not include one in the API response.

## Current State

Shipped baseline:

- Slack Mirror corpus search returns stable native Slack identifiers.
- Slack Mirror corpus search returns `channel_name` alongside `channel_id` for
  the observed result rows.
- Receipts can render channel names from the existing search payload and can
  suppress ID-looking labels from primary result cards.

Remaining work:

- None for the first pass. Slack Mirror corpus search now includes
  `user_label`, `user_name`, and `user_display_name` when matching user profile
  rows are available. Context-pack rows already emitted `user_label` from the
  same user table join.
- Future work can add archived/historical display-name snapshots if current
  profile labels prove insufficient for long-lived evidence review.

## Observed Payload Gap

Receipts checked the live child API through its BFF:

```bash
curl -sS 'http://receipts.localhost/api/children/slack/v1/search/corpus?limit=3&mode=hybrid&query=report'
```

For current matching rows, the response includes:

- `channel_id`: present, for example `C0AHHG09TEU`
- `channel_name`: present, for example `oc-dev-slack-export`
- `user_id`: present, for example `U0AC4G11SH3`
- `user_label`, `user_name`, `user_display_name`, `sender_label`: absent

Receipts can therefore render the channel as `#oc-dev-slack-export`, but it
must currently render the participant as a generic `Slack participant` rather
than a real human-readable sender name.

## Requested Slack Work

Add stable human-facing identity labels to Slack corpus search and context-pack
payloads while preserving native IDs for evidence/provenance.

Preferred fields:

- `user_id`: stable Slack user ID, unchanged
- `user_label`: human-facing display name for UI use
- `user_name`: Slack username or handle when display name is unavailable
- `user_display_name`: explicit Slack profile display name when available

Equivalent names such as `sender_label` are acceptable if documented and
consistent across search results and context-pack rows.

For channel identity, continue returning both:

- `channel_id`: stable Slack channel ID
- `channel_name`: human-facing channel name

For text rendering, prefer returning Slack text in a form that still preserves
machine refs but includes resolvable labels, for example:

- `<@U123|Jane Doe>` rather than only `<@U123>`
- `<#C123|oc-dev-slack-export>` rather than only `<#C123>`

Receipts can decode common Slack mrkdwn and emoji shortcodes, but Slack Mirror
is the only layer that can reliably pair provider IDs with current or archived
human labels.

## Boundary

Slack Mirror should continue to own:

- Slack user/channel identity resolution
- historical label snapshots when names change
- raw Slack IDs under native/source refs
- corpus search and context-pack payload semantics

Receipts should continue to own:

- shared display normalization
- hiding technical IDs from primary result cards
- preserving native IDs in provenance, source refs, and extensions

## Acceptance

Receipts should be able to call:

- `GET /v1/search/corpus`
- `POST /v1/search/context-pack`

and render:

- sender names as human-readable labels, not `U...` IDs
- channel names as human-readable labels, not `C...` IDs
- common emoji shortcodes as emoji in snippets and context text
- native Slack IDs only in provenance/details, not the primary scan path

## Validation

Implemented and validated on 2026-04-25:

- `uv run python -m unittest tests.test_search.SearchTests.test_search_corpus_combines_messages_and_derived_text tests.test_api_server.ApiServerTests.test_search_endpoints -v`
- `python -m py_compile slack_mirror/search/sqlite_adapter.py slack_mirror/search/corpus.py slack_mirror/service/app.py tests/test_search.py tests/test_api_server.py`
- planning contract audit returned `ok: true`
- `git diff --check`
- live Slack API curl confirmed corpus search rows now include `user_label:
  OpenClaw`, `user_name: openclaw`, and `user_display_name: OpenClaw`
- live Receipts BFF curl confirmed the same fields pass through
- `agent-browser` verified Receipts Cards mode renders `OpenClaw` instead of
  the Slack `U...` user ID

## Next Recommended Action

Update Receipts-side display fixtures or smoke expectations if the parent repo
adds explicit assertions for human-readable Slack sender labels.
