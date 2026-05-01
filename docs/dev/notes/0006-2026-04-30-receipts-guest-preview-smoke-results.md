# 0006 | Receipts guest preview smoke results

Date: 2026-04-30
From: Slack Export / Slack Mirror
Audience: Receipts maintainers

## Context

Slack Mirror commit `1dec26e` added guest-safe Slack user mention rendering for
Receipts-facing preview text:

- corpus search message rows now expose rendered `matched_text`
- selected-result context/event `text` now uses rendered labels
- changed selected-result context rows preserve `raw_text`
- unresolved mentions render as `@unresolved-slack-user`

## Live Smoke Evidence

Direct Slack child API smoke:

- `GET http://127.0.0.1:8787/v1/search/corpus?workspace=default&query=Vacuum%20Oven%20%238&limit=3&mode=lexical`
- raw `text` retained Slack-native `<@UEHFF497A>`
- `matched_text` rendered `@Andrew Becker`
- no `@Slack user` fallback appeared in the rendered text

Receipts Slack BFF lifecycle smoke:

- `npm run smoke:slack-bff -- --slack-base-url http://127.0.0.1:8787 --query 'website service' --skip-build`
- passed `slack_bff_full_lifecycle`
- hit: `message|default|CKFCY8SMP|1635343080.002900`
- created and deleted temporary export:
  `receipts-slack-bff-smoke-1777595355-renamed`

Receipts guest-grant payload smoke:

- started Receipts on a throwaway state store at `http://127.0.0.1:4201`
- logged into the Slack child API through `/api/receipts/slack/env-login`
- searched live Slack through `/api/children/slack/v1/search/corpus`
- created a throwaway guest grant using the live Slack preview snippet
- resolved `/api/receipts/guest/{token}`
- resolved guest target preview contained `@Nacu`
- resolved guest target preview did not contain raw `<@...>` or `@Slack user`

## Receipts Follow-Up

`npm run smoke:slack-bff -- --query 'Vacuum Oven #8'` correctly demonstrated
Slack's new mention rendering in `matched_text`, but the smoke failed before
the lifecycle step because its assertion requires a human-readable sender
`user_label`. The top result is a bot-authored Slack form post where
`user_label` is absent by design, while the form body mention rendered
correctly as `@Andrew Becker`.

Recommended Receipts-side update:

- keep the sender-label assertion for human-authored results
- add a separate assertion for preview text: `matched_text` should not contain
  raw `<@...>` or generic `@Slack user`
- allow bot-authored results to pass when the display preview text is
  guest-safe and provenance still preserves native IDs
