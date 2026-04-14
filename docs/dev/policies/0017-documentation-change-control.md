# Policy | Documentation Change Control

## Policy

- Keep the live planning and execution docs current in the same slice as the code or behavior change.
- If scope, semantics, service contracts, or operator workflows change, update the corresponding user-facing or governing docs before handoff.
- Preserve completed or superseded plans as durable history instead of deleting them outright.
- Do not rely on chat history as the authoritative explanation of why a change happened; record it in the repo docs.
- When a change affects a narrow contract document, update that contract doc in the same slice rather than deferring it to later cleanup.
## Adoption Notes

Use this module when the repo:
- has roadmap, runbook, journal, contract, or execution-plan docs that steer work
- needs docs to stay aligned with semantics or operator behavior
- benefits from explicit anti-drift rules for plan and doc maintenance
