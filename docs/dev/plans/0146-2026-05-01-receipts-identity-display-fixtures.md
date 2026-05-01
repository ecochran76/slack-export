# 0146 | Receipts identity display fixture coverage

State: CLOSED

Roadmap: P12

## Context

Receipts homework H4 asks Slack Export to keep guest-facing identity and display
rendering child-owned. Receipts should receive human-readable labels and display
text, while Slack Export preserves raw Slack IDs, timestamps, mrkdwn, and
provenance fields for audit/debugging.

## Current State

Shipped baseline:

- Corpus search message rows expose `matched_text` with guest-safe user mention
  rendering and retain raw Slack `text`.
- Selected-result context rows and event projections render user mentions in
  `text` and preserve `raw_text` plus `text_rendering` when rendering changes
  the string.
- Context-window rows expose sender labels, native IDs, source refs, and action
  targets.

Shipped in this slice:

- Rendered common Slack emoji aliases in the same guest-facing display text
  lane.
- Applied guest-safe display rendering to context-window row text as well as
  context-pack/export rows.
- Added fixture coverage for normal human-authored, bot-authored, unresolved, and
  redacted/deleted-style rows while preserving raw provenance.

Remaining work:

- Broaden emoji alias coverage later if real corpus evidence shows an alias
  outside the built-in common set is important for guest display.

## Scope

- Extend Slack display-text rendering in `slack_mirror.core.slack_text`.
- Reuse that rendering in corpus search, selected-result context packs, and
  context windows.
- Add targeted tests for identity/display fields and raw provenance.
- Update docs and planning state.

## Non-Goals

- Do not implement a full Slack mrkdwn renderer.
- Do not make Receipts infer Slack identity from raw IDs.
- Do not expose guest access to search/list/mutation routes.

## Acceptance

- Search results, context-window rows, selected-result artifacts, and event
  payloads expose guest-safe display text for known mentions and common emoji
  aliases.
- Raw Slack mrkdwn is preserved where display rendering changes the text.
- Fixtures cover human, bot, unresolved mention, and redacted/deleted-style
  messages.

## Validation

Passed:

- `./.venv/bin/python -m py_compile slack_mirror/core/slack_text.py slack_mirror/service/app.py slack_mirror/search/corpus.py tests/test_app_service.py tests/test_search.py`
- `./.venv/bin/python -m unittest tests.test_search.SearchTests.test_search_corpus_combines_messages_and_derived_text tests.test_app_service.AppServiceTests.test_receipts_identity_display_fixture_preserves_guest_safe_text_and_raw_provenance -v`
- `./.venv/bin/python -m unittest tests.test_app_service.AppServiceTests.test_create_selected_result_export_writes_context_artifact_and_manifest tests.test_app_service.AppServiceTests.test_build_context_window_pages_channel_messages_with_opaque_cursors tests.test_api_server.ApiServerTests.test_search_endpoints -v`
- `./.venv/bin/python scripts/smoke_receipts_compatibility.py --json`
- `/home/ecochran76/.local/share/slack-mirror/venv/bin/python -m pip install -e /home/ecochran76/workspace.local/slack-export`
- `systemctl --user restart slack-mirror-api.service && sleep 1 && curl -sS http://127.0.0.1:8787/v1/health`
- `./.venv/bin/python scripts/smoke_receipts_compatibility.py --base-url http://127.0.0.1:8787 --query "website service" --json`
- `python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json`
- `git diff --check`

## Next Recommended Action

After H4 lands, continue H3 event readiness/lifecycle expansion so Receipts Live
View can explain current, empty, degraded, and behind states without log
scraping.
