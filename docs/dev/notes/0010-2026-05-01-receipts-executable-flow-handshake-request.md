# 0010 | Receipts executable-flow handshake request

Date: 2026-05-01
From: Receipts
Audience: Slack Export / Slack Mirror maintainers

## Context

Receipts has completed a no-dispatch guardrail pass for Slack tenant
maintenance actions.

Relevant Receipts artifacts:

- `../receipts/docs/dev/notes/0024-2026-05-01-slack-tenant-executable-flow-design-review.md`
- `../receipts/docs/dev/plans/0075-2026-05-01-slack-tenant-mutation-promotion-checklist.md`
- `../receipts/docs/dev/plans/0080-2026-05-01-slack-tenant-disabled-execute-no-write-smoke.md`
- `../receipts/docs/dev/plans/0081-2026-05-01-slack-tenant-executable-flow-design-review.md`

Receipts currently renders Slack tenant maintenance metadata, prepares actions
from fresh `/v1/tenants` state, previews same-origin proxied request method and
path, and browser-smokes that the execute control remains disabled and
non-writing. Even with the Receipts parent feature flag enabled,
`data-executable="false"` and the synthetic child mutation count remains zero.

## Request

Please confirm or implement the child-owned executable-flow handshake that
Receipts needs before opening any Slack tenant mutation dispatch path.

Receipts should not implement a BFF dispatch function until Slack Export
answers the contract questions below in docs and, where needed, API/profile
fields.

## Contract Questions

### Session And CSRF

- Does `GET /auth/session` distinguish all states Receipts should branch on:
  authenticated, unauthenticated, expired, insufficient permission, and
  CSRF/nonce required?
- Does Receipts need to forward or request a CSRF token, nonce, or custom
  header for tenant maintenance writes?
- If CSRF metadata is required, where should Receipts read it from:
  `/auth/session`, `/v1/service-profile`, a dedicated endpoint, or a response
  header?
- Are cookie-only child-session credentials sufficient for same-origin
  `/api/children/slack/...` writes after the Receipts BFF rewrites origin and
  referer?

### Action Metadata

- Are these fields stable for every executable tenant action:
  `id`, `label`, `method`, `path` or `routeTemplate`, `enabled`,
  `disabledReason`, `requiresConfirmation`, `confirmationValue`, `dangerous`,
  and safe `bodyTemplate` metadata?
- Should Receipts treat `maintenance_actions` from `/v1/tenants` as the only
  executable source of truth, with profile-level action descriptors remaining
  non-executable templates?
- Are there any action-specific body fields Receipts may let an operator edit,
  or should the first dispatch implementation only send Slack-provided
  defaults plus typed confirmation values?

### Mutation Response Shape

- What safe response fields should tenant mutation routes return for Receipts
  UI and parent audit display?
- Can responses consistently include a status, child operation id when
  available, safe message, and machine-readable error code?
- Please define expected error codes or categories for auth failure, CSRF or
  session failure, child validation failure, runtime failure, conflict, and
  unexpected response shape.
- Which response fields are safe for Receipts to persist in parent-side
  operation history?

### Idempotency And Duplicate Clicks

- Should Receipts send an idempotency key for tenant maintenance writes?
- If yes, what header or body field should carry it?
- If no, can Slack Export guarantee duplicate UI clicks are harmless or
  rejected clearly while an action is already running?
- What should Receipts show for a duplicate, in-flight, or already-completed
  tenant action?

### Post-Action Refresh

- After each action, should Receipts refresh `/v1/tenants`, `/v1/tenants/{name}`,
  `/v1/runtime/status`, or a different endpoint?
- Should the child mutation response include a `refresh` recommendation or
  follow-up URL list?
- Are any actions asynchronous enough that Receipts should display a queued or
  pending state after the first refresh?

## Receipts Stop Rule

Until Slack Export confirms this handshake, Receipts will keep Slack tenant
execution hard-disabled:

- no BFF dispatch route or function;
- no executable button;
- no mutation POST from Receipts;
- `data-executable="false"`;
- `data-child-response-status="not_dispatched"`;
- no-write browser smoke remains required.

## Suggested Slack Export Next Slice

Add or update a Slack Export plan/API contract section that answers the
questions above. If API/profile changes are needed, prefer adding explicit
machine-readable fields to `/v1/service-profile`, `/auth/session`,
`/v1/tenants`, and mutation responses rather than relying on prose-only
conventions.

## Validation Expected From Slack Export

At minimum, please run:

```bash
python /home/ecochran76/workspace.local/agent-policies/repo-policy-selector/scripts/audit_planning_contract.py --repo-root /home/ecochran76/workspace.local/slack-export --json
git diff --check
```

If API fields or response shapes change, also run the targeted API tests and
`./.venv/bin/python scripts/smoke_receipts_compatibility.py --json`.
