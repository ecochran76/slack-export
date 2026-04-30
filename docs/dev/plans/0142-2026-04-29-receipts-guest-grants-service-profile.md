# 0142 | Receipts guest grants service profile

State: CLOSED

Roadmap: P12

## Purpose

Expose Slack Mirror's guest-grant artifact route policy in `GET
/v1/service-profile` so Receipts can determine report guest-sharing readiness
without parsing Slack docs or route names.

## Current State

Receipts handoff note
`docs/dev/notes/0004-2026-04-29-receipts-guest-grants-route-policy.md`
observed that Slack Mirror already advertises `capabilities.guestGrants: true`
and accepts Receipts guest-grant assertion headers on export/artifact reads,
but does not yet include a concrete `guestGrants` route-policy object in the
child service profile.

## Scope

- Add a concrete `guestGrants` policy object to `/v1/service-profile`.
- Mark only export/report artifact read routes as guest-safe.
- Mark list/search/create/rename/delete routes as local-only/operator routes.
- Document the profile object in the API/MCP contract.
- Cover the policy object with API tests.

## Non-goals

- Do not change export storage or artifact authorization ownership.
- Do not make search, list, mutation, tenant, runtime, or workspace routes
  guest-safe.
- Do not move guest-grant signing/enforcement into Receipts.
- Do not add a new route.

## Acceptance

- `/v1/service-profile` includes `guestGrants.assertionsUnderstood: true`.
- Every advertised guest-safe route includes `methods`, `routeTemplate`,
  `guestSafe: true`, `honorsAssertion: true`, and `targetKinds`.
- Local-only routes include route templates and reasons.
- Existing service-profile tests pass.
- Planning audit, `git diff --check`, and release check pass.

## Result

Implemented the concrete `guestGrants` route-policy object in
`GET /v1/service-profile`.

Guest-safe routes are limited to export/report artifact reads:

- `GET /exports/{exportId}`
- `GET /exports/{exportId}/{path}`
- `GET /exports/{exportId}/{path}/preview`
- `GET /v1/exports/{exportId}`

Local-only routes explicitly include export listing, export creation, export
rename, export deletion, and search. Slack Mirror continues to own export
storage, artifact authorization, and optional HMAC verification through
`SLACK_MIRROR_RECEIPTS_CHILD_GRANT_SHARED_SECRET` or
`RECEIPTS_CHILD_GRANT_SHARED_SECRET`.

Managed runtime was refreshed and `slack-mirror-api.service` was restarted.
`curl http://127.0.0.1:8787/v1/service-profile` returned `ok: true` with
`guestGrants.assertionsUnderstood: true` and the expected guest-safe/local-only
route policy.
