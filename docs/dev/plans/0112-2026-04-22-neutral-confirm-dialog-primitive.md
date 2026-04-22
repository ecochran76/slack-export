# 0112 | Neutral Confirm Dialog Primitive

State: CLOSED

Roadmap: P09 Tenant Onboarding Wizard And Settings

## Current State

The React tenant workbench now supports several narrow tenant mutations, but
`Stop live sync` remains intentionally disabled because it is disruptive and
needs an explicit confirmation pattern first.

This slice adds that confirmation primitive without wiring any destructive
tenant action yet.

## Scope

- Add a neutral `ConfirmDialog` component.
- Support title, message, optional details, cancel and confirm actions, tone,
  and optional typed confirmation text.
- Expose a non-mutating tenant-workbench preview button so the component can be
  smoke-tested in the current app shell.
- Keep `Stop live sync` disabled until a separate mutation slice.

## Non-Goals

- Do not wire stop, retire, delete, or other destructive tenant mutations.
- Do not add global dialog routing or portal infrastructure.
- Do not extract a shared package yet.

## Acceptance Criteria

- The primitive is provider-neutral and does not import tenant types.
- The preview dialog opens and closes without calling a tenant API.
- Typed confirmation gates the confirm button when `expectedText` is provided.
- Existing frontend validation and browser smoke pass.

## Definition Of Done

- `frontend/src/components/ConfirmDialog.tsx` exists and is used by
  `TenantWorkbench` only as a preview.
- Frontend contract docs describe the primitive and extraction gate.
- `ROADMAP.md` and `RUNBOOK.md` are updated.
- The slice is committed independently.
