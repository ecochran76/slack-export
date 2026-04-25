# 0122 | Receipts child service profile homework

State: OPEN

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

- Slack Mirror does not yet expose one machine-readable profile that declares
  those capabilities, auth requirements, query operators, artifact links, and
  UI affordance hints for a shared parent frontend.
- Receipts therefore still has to carry Slack-specific knowledge in its adapter
  until the shared child-service profile contract lands.

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

This note is documentation-only. The future implementation slice should add a
focused Slack API test for the profile route and update the Receipts
Slack-BFF smoke once Receipts consumes the profile.

## Next Recommended Action

Wait for Receipts to land the first shared `ChildServiceProfile` contract, then
add the smallest Slack route or documented payload that satisfies that contract.
