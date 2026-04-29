# Receipts Guest Grant Route Policy Handoff

Date: 2026-04-29
Audience: Slack Export / Slack Mirror
From: `../receipts`

## Why This Note Exists

Receipts now renders a cross-child Reports Guest Bundle policy strip. It can
read concrete child `guestGrants` route-policy objects from child service
profiles and use them to show whether created report artifacts are safe for a
parent-owned guest link.

Current Receipts state:

- commit `537585f feat(web): gate im guest bundle sharing`
- commit `ad6e2fd feat(web): summarize child guest policy readiness`
- plan `../receipts/docs/dev/plans/0046-2026-04-29-cross-child-guest-policy-readiness.md`

Observed Slack state:

- `GET /v1/service-profile` advertises `capabilities.guestGrants: true`.
- Slack Mirror already documents and accepts Receipts guest-grant assertion
  headers on export artifact reads.
- The service profile does not yet include a concrete `guestGrants` route
  policy object, so Receipts shows Slack report artifacts as a pending
  route-policy handoff gap.

## Requested Slack Work

Add a concrete `guestGrants` object to `GET /v1/service-profile` so Receipts
does not need to infer Slack guest sharing semantics from docs or route names.

Suggested shape, matching the child profile contract Receipts already consumes:

```json
{
  "capabilities": {
    "guestGrants": true
  },
  "guestGrants": {
    "assertionsUnderstood": true,
    "defaultBehavior": "local_only_unless_route_allows_guest_grant",
    "permissions": {
      "currentlyEnforced": false,
      "recognized": ["view", "download", "open-artifact"]
    },
    "routes": [
      {
        "methods": ["GET"],
        "routeTemplate": "/exports/{exportId}",
        "guestSafe": true,
        "honorsAssertion": true,
        "targetKinds": ["artifact", "report-artifact"]
      },
      {
        "methods": ["GET"],
        "routeTemplate": "/exports/{exportId}/{path}",
        "guestSafe": true,
        "honorsAssertion": true,
        "targetKinds": ["artifact", "report-artifact"]
      },
      {
        "methods": ["GET"],
        "routeTemplate": "/exports/{exportId}/{path}/preview",
        "guestSafe": true,
        "honorsAssertion": true,
        "targetKinds": ["artifact", "report-artifact"]
      },
      {
        "methods": ["GET"],
        "routeTemplate": "/v1/exports/{exportId}",
        "guestSafe": true,
        "honorsAssertion": true,
        "targetKinds": ["artifact", "report-artifact"]
      }
    ],
    "localOnlyRoutes": [
      {
        "methods": ["GET"],
        "routeTemplate": "/v1/exports",
        "reason": "Export listing remains a child-session/operator route."
      },
      {
        "methods": ["POST"],
        "routeTemplate": "/v1/exports",
        "reason": "Export creation mutates Slack-owned artifact state."
      },
      {
        "methods": ["POST"],
        "routeTemplate": "/v1/exports/{exportId}/rename",
        "reason": "Export rename mutates Slack-owned artifact state."
      },
      {
        "methods": ["DELETE"],
        "routeTemplate": "/v1/exports/{exportId}",
        "reason": "Export deletion mutates Slack-owned artifact state."
      },
      {
        "methods": ["GET"],
        "routeTemplate": "/v1/search",
        "reason": "Search exposes corpus data outside a selected report bundle."
      }
    ],
    "signatureModes": {
      "accepted": ["unsigned", "hmac-sha256"],
      "productionRecommended": "hmac-sha256"
    },
    "targetKinds": ["artifact", "report-artifact"]
  }
}
```

If Slack requires signed assertions in a deployment, keep that enforcement
child-side and expose the relevant environment variable names in nearby
documentation. Receipts already sends `hmac-sha256` signatures when
`RECEIPTS_CHILD_GRANT_SHARED_SECRET` is configured.

## Guardrails

- Do not move Slack report/export storage, search, native Slack auth, or
  artifact authorization into Receipts.
- Do not make list, search, create, rename, delete, runtime, workspace, or
  tenant routes guest-safe just because export artifact reads are guest-safe.
- Do not require Receipts to parse Slack route internals or docs to decide
  guest readiness.

## Suggested Validation

- Unit/API test that `GET /v1/service-profile` includes
  `guestGrants.assertionsUnderstood: true`.
- Test that every advertised guest-safe route has `methods`, `routeTemplate`,
  `guestSafe: true`, `honorsAssertion: true`, and `targetKinds`.
- Existing guest-grant header tests should continue proving:
  - unsigned local-dev behavior when no shared secret is configured;
  - signed assertion enforcement when a shared secret is configured.
- Receipts smoke after the Slack change:
  - create a Slack selected-result export through Receipts;
  - open Reports Guest Bundle;
  - confirm Slack row changes from pending route-policy gap to ready.

