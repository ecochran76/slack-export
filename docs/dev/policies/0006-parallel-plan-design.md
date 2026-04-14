# Policy | Parallel Plan Design

## Policy

- Give each parallel lane a clear owner, bounded scope, and expected write surface.
- Keep the critical path visible so parallel work does not hide the real blocker.
- Prefer plan slices that minimize cross-lane file overlap and reconciliation cost.
- Call out integration points explicitly when multiple lanes must converge before completion.
- Do not open parallel lanes just because tools allow delegation; open them only when the work can move independently.
- If a lane becomes coordination-heavy, collapse it back into the critical path or redefine the lane boundary.
## Adoption Notes

Use this module when repos regularly use subagents, parallel contributors, or multiple active implementation lanes.

Execution-bias guidance:
- `max-dev-speed`: open more parallel lanes when ownership and write surfaces are clear enough to keep wall-clock time down
- `balanced`: parallelize bounded sidecar work but keep urgent blockers and tightly coupled work on the critical path
- `max-token-efficiency`: keep fewer active lanes, prefer larger local ownership, and avoid parallel decomposition that duplicates context or creates heavy reconciliation work
