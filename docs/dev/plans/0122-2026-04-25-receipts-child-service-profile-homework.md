# 0122 | Receipts child service profile homework

State: CLOSED

Roadmap: P12

## Context

`../receipts` is becoming the shared frontend and report/search workbench for
Slack Mirror, Ragmail, and imcli. The current Receipts integration proves that
Slack Mirror can be treated as a backend child service through the Receipts BFF:

- health is reachable through the child proxy
- child-owned frontend auth/session is proxied through Receipts
- corpus search and selected-result context are live
- managed selected-result exports can be created, listed, opened, renamed, and
  deleted through the protected child API session

The next convergence step should make those capabilities discoverable rather
than hardcoded in the parent UI.

## Current State

Shipped baseline:

- Slack Mirror already exposes the API surfaces Receipts is using for health,
  auth/session passthrough, corpus search, selected-result context, and managed
  selected-result export lifecycle.
- Receipts can validate Slack BFF behavior through its own `npm run
  smoke:slack-bff` path, including credential-backed export create/list/open/
  rename/delete when local Slack frontend credentials are supplied.

Remaining work:

- Receipts still needs to consume the live Slack profile through its BFF path
  instead of the parent-authored profile template.
- Future Slack profile changes should stay additive unless Receipts has already
  migrated to a newer contract version.

## Boundary

Slack Mirror continues to own:

- Slack runtime behavior, DB schema, sync, search, export storage, and
  protected child API sessions
- selected-result export bundle lifecycle semantics
- Slack-native report rendering and artifact URLs
- Slack-specific search operators, workspace scopes, file/canvas evidence, and
  auth policy

Receipts should own:

- shared frontend orchestration
- provider-neutral child-service capability contracts
- cross-child UI behavior based on explicit service capabilities
- parent-side adapter logic that calls Slack Mirror's API instead of wrapping
  Slack Mirror's frontend

## Requested Slack Homework

Add or document a stable child-service profile/capabilities response. A concrete
route such as `GET /v1/service-profile` is preferable, but an equivalent
documented route is fine if it is stable and machine-readable.

The response should let Receipts render Slack controls without hardcoded
knowledge of Slack Mirror internals. It should include:

- service identity: stable service key, display/product names, version, and
  optional future rename hint such as `slack-receipts`
- auth/session profile: child-session requirement, session/login/logout links,
  unauthenticated error code, and same-origin proxy expectations
- search capabilities: route links, supported scopes, retrieval modes, portable
  query operators, lossy operators, native extension operators, and
  `action_target` support
- selected-result report/export capabilities: create, list, open, rename,
  delete, stable report/manifest/raw JSON link relations, artifact file types,
  lifecycle permissions, and retention constraints
- source/evidence metadata: count fields, timestamps, workspace/channel labels,
  selected-result counts, and native/source refs for Slack IDs and permalinks
- UI affordance hints: preferred icon key such as `slack`, labels, optional
  color/accent hints, and feature flags for visible controls

## Shape Sketch

Receipts does not require this exact schema yet, but this is the likely level of
detail:

```json
{
  "serviceKey": "slack",
  "displayName": "Slack",
  "productName": "Slack Mirror",
  "serviceRenameTarget": "slack-receipts",
  "version": "0.0.0",
  "auth": {
    "mode": "child_session",
    "sessionUrl": "/auth/session",
    "loginUrl": "/auth/login",
    "logoutUrl": "/auth/logout",
    "unauthenticatedCode": "AUTH_REQUIRED"
  },
  "capabilities": {
    "health": true,
    "corpusSearch": true,
    "contextPack": true,
    "selectedResultExportCreate": true,
    "selectedResultExportList": true,
    "selectedResultExportOpen": true,
    "selectedResultExportRename": true,
    "selectedResultExportDelete": true
  },
  "queryOperators": [
    {"name": "before", "support": "supported"},
    {"name": "after", "support": "supported"},
    {"name": "participant", "support": "lossy"},
    {"name": "slack.channel", "support": "native"}
  ],
  "artifacts": {
    "listUrl": "/v1/exports",
    "itemUrlTemplate": "/exports/{exportId}",
    "manifestUrlTemplate": "/exports/{exportId}/manifest.json",
    "supportedTypes": ["html", "json", "manifest", "attachment"]
  }
}
```

## Acceptance For Receipts

Receipts should be able to:

- fetch the Slack child-service profile through the same BFF path it already
  uses for Slack API routes
- render Slack source cards, search controls, sign-in state, selected-result
  report actions, and artifact-vault controls from declared capabilities
- avoid calling Slack Mirror's frontend as an API surface
- keep Slack-specific evidence visible through native refs and extensions
  without forcing Ragmail or imcli to mimic Slack-only concepts

## Validation

Slack Mirror now exposes `GET /v1/service-profile` as the stable
machine-readable profile route. The implementation includes a focused API test
for the profile payload. Receipts still needs to update its Slack-BFF smoke once
it consumes the live profile.

## Next Recommended Action

Update Receipts to fetch the live Slack child-service profile through its
existing BFF path, replacing the parent-authored Slack capability template.
