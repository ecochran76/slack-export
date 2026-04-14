# Policy | Subagent Workflow Optimization

## Policy

- Delegate only concrete, bounded subtasks that materially advance the active slice.
- Keep urgent blocking work local when the next action depends directly on the answer.
- Give delegated work explicit ownership, expected output, and write scope.
- Prefer subagents for independent sidecar work, verification, or implementation slices with disjoint write sets.
- Do not spawn parallel work that duplicates context loading or repeats the same exploration without a clear benefit.
- Reuse prior agent context when the task is a continuation of the same bounded thread.
- Keep final integration responsibility with the primary agent even when subagents perform part of the work.
- Be explicit about whether the repo optimizes for wall-clock speed, token efficiency, or a balance of the two.
## Adoption Notes

Use this module when repos actively rely on delegation or subagent orchestration rather than single-agent execution.

Execution-bias guidance:
- `max-dev-speed`: delegate earlier, parallelize more independent work, and accept some coordination overhead to reduce wall-clock time
- `balanced`: delegate bounded sidecar work and verification, but keep tightly coupled or critical-path work local
- `max-token-efficiency`: delegate only when the subtask is clearly independent and the expected gain exceeds the added context and reconciliation cost
