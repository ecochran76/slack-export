# 0125 | Receipts guest grant assertion handoff

State: CLOSED

Roadmap: P12

## Purpose

Receipts now owns parent guest-link creation, token hashing, grant auditing, and
guest chrome. Slack Mirror should continue to own Slack export/report storage,
browser auth/session enforcement, workspace authorization, and native Slack
provenance.

Canonical Receipts note:
`../receipts/docs/dev/notes/0015-2026-04-26-child-guest-grant-enforcement.md`

Receipts commit:
`2aca4d1 feat: forward guest grant assertions`

## Current State

Receipts opens granted child report artifacts through:

```text
GET /api/receipts/guest/{token}/targets/{target_id}/open
```

The parent BFF validates the guest token and target, appends a
`grant-target-open` audit event, and fetches the child-owned relative artifact
path server-side. The browser never receives Slack's stored child link, the raw
guest token hash, or a local artifact path.

For Slack, this applies to managed export/report artifact reads such as the
HTML export URL or future selected-result artifact readers that Receipts opens
through the child BFF path.

Slack Mirror now accepts these assertions on export/artifact read routes only:

- `GET /exports/{exportId}`
- `GET /exports/{exportId}/{path}`
- preview reads under the same export bundle route
- `GET /v1/exports/{exportId}`

Normal child-session auth still applies to export listing, create, rename,
delete, runtime reports, workspace, tenant, search, and other protected routes.

## Requested Slack Mirror Work

- Add a narrow parser for Receipts guest-grant assertion headers on export or
  selected-result artifact read routes.
- Treat `x-receipts-request-mode: guest-grant` as a parent assertion that
  Receipts already validated the guest token and target.
- Preserve Slack-owned checks:
  - export/artifact id exists;
  - workspace and tenant scope are valid;
  - export belongs to the expected managed-export namespace;
  - native Slack authorization/session behavior still applies where the route
    requires it.
- Do not require exposing Slack frontend credentials or Slack session cookies
  to guest browsers.
- In deployments where Slack artifact routes can be reached by anything other
  than the Receipts BFF, require signed mode and verify the HMAC before
  treating the request as a Receipts guest-grant read.

## Forwarded Headers

Receipts forwards:

```text
x-receipts-request-mode: guest-grant
x-receipts-child-service: slack
x-receipts-guest-grant-id: grant-...
x-receipts-guest-grant-target-id: ...
x-receipts-guest-grant-target-kind: report-artifact | artifact
x-receipts-guest-grant-token-id: tok-...
x-receipts-guest-grant-scope: result-set | artifact-download | report-bundle
x-receipts-guest-grant-audience: guest-link | named-user | group
x-receipts-guest-grant-permissions: comma,separated,permissions
x-receipts-guest-grant-ts: ISO-8601 timestamp
x-receipts-guest-grant-nonce: UUID
x-receipts-guest-grant-signature-mode: unsigned | hmac-sha256
x-receipts-guest-grant-signature: hex hmac, when signed
```

Receipts does not forward raw guest tokens or token hashes.

## Signing

Unsigned mode is for trusted local development. Signed mode uses the shared
secret configured in Receipts as `RECEIPTS_CHILD_GRANT_SHARED_SECRET`.
Slack Mirror can use the same environment name or a Slack-specific alias that
maps to the same secret.

The HMAC-SHA256 payload is newline-joined in this exact order:

```text
method
service
child path plus query
grant id
target id
token id
timestamp
nonce
```

For the current Receipts opener, `method` is `GET`.

## Guardrails

- Do not move Slack export rendering, report generation, workspace search, or
  native auth/session logic into Receipts.
- Do not make Slack Mirror depend on Receipts for ordinary authenticated export
  reads.
- Do not log raw guest tokens. Token ids are safe for audit correlation; raw
  token values and hashes are not.
- Preserve native Slack IDs under provenance fields instead of treating
  Receipts grant ids as Slack-native artifact ids.

## Suggested Validation

- Unit coverage for parsing unsigned guest-grant assertion headers.
- Unit coverage for rejecting missing or malformed signed assertions when
  signed mode is required.
- Unit coverage for HMAC verification using the documented payload order.
- API smoke where Receipts opens a granted Slack export and Slack observes
  `x-receipts-request-mode: guest-grant` without receiving a raw guest token.
- Existing protected export/session tests should continue to pass for normal
  authenticated Slack reads.

## Status

CLOSED. Slack Mirror parses Receipts guest-grant assertions on export/artifact
read routes, allows unsigned local-development assertions when no shared secret
is configured, and requires/verifies HMAC-SHA256 signatures when
`SLACK_MIRROR_RECEIPTS_CHILD_GRANT_SHARED_SECRET` or
`RECEIPTS_CHILD_GRANT_SHARED_SECRET` is configured.
