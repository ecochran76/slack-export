# 0143 | Guest-safe mention rendering for Receipts previews

State: CLOSED

Roadmap: P12

## Context

`../receipts` validated a real Reports Guest Bundle flow and left
`docs/dev/notes/0005-2026-04-30-receipts-guest-preview-mention-labels.md` as
the Slack-owned follow-up. The parent guest preview can already render Slack
title, location, participant, and timestamp fields, but snippets built from
Slack text can still degrade to generic `@Slack user` placeholders when Slack
Mirror returns raw `<@U...>` mentions without display labels.

## Current State

Shipped baseline:

- Slack Mirror corpus search and selected-result context packs preserve native
  Slack IDs for provenance.
- Slack Mirror returns sender/channel display labels when matching user and
  channel rows are available.
- Receipts can normalize Slack mrkdwn labels but must not guess Slack identity
  mappings.

Shipped in this slice:

- Emit guest-safe rendered mention text in the existing display fields Receipts
  consumes for previews.
- Preserve raw Slack text separately when rendering changes the string.
- Use a deterministic unresolved placeholder so generic parent-side fallbacks do
  not hide lookup failures.

## Acceptance

- Corpus search message rows expose `matched_text` with `<@U...>` mentions
  rendered to `@Display Label` when the local Slack user table resolves the ID.
- Selected-result context rows and neutral event text expose guest-safe mention
  rendering in `text`.
- Raw text is retained as `raw_text` when rendering changes the string.
- Unresolved user mentions render as `@unresolved-slack-user`, not generic
  `@Slack user`.
- Unit tests cover search and selected-result export behavior.

## Validation

- `./.venv/bin/python -m unittest tests.test_app_service.AppServiceTests.test_create_selected_result_export_writes_context_artifact_and_manifest tests.test_search.SearchTests.test_search_corpus_combines_messages_and_derived_text -v`
- `./.venv/bin/python -m unittest tests.test_app_service.AppServiceTests.test_create_selected_result_export_writes_context_artifact_and_manifest tests.test_search.SearchTests.test_search_corpus_combines_messages_and_derived_text tests.test_api_server.ApiServerTests.test_search_endpoints -v`
- `./.venv/bin/python -m py_compile slack_mirror/core/slack_text.py slack_mirror/service/app.py slack_mirror/search/corpus.py tests/test_app_service.py tests/test_search.py`
- `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
- `git diff --check`
- managed editable install refresh
- `systemctl --user restart slack-mirror-api.service`
- live `/v1/service-profile` and `/v1/health` curls returned `ok: true`
- direct live Slack child search confirmed raw `text` preserved `<@UEHFF497A>`
  while rendered `matched_text` exposed `@Andrew Becker`
- Receipts Slack BFF lifecycle smoke passed with query `website service`
- throwaway Receipts guest-grant payload smoke resolved a live Slack preview
  containing `@Nacu` with no raw `<@...>` or `@Slack user`

## Next Recommended Action

After this slice lands, ask Receipts to consume `matched_text` and context-pack
`text` from a fresh Slack search/export smoke and confirm the guest preview no
longer shows avoidable `@Slack user` placeholders.
