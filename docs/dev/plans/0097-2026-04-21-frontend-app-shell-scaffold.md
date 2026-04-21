# 0097 | Frontend App Shell Scaffold

State: CLOSED

Roadmap: P09

## Current State

- `0051` selected Vite, React, TypeScript, and a reusable operator UI layer as the preferred operator-console architecture.
- `0096` added provider-neutral selected-result contracts under `frontend/src/contracts/`.
- Before this slice, the repo had no `package.json`, Vite entrypoint, React app shell, theme token files, or build command for the frontend worktree.
- The frontend worktree now has a minimal Vite/React/TypeScript package, theme-token files, shell/navigation primitive, metric-strip primitive, and a selected-result placeholder screen that consumes the new contracts.

## Scope

- Add a minimal frontend package under `frontend/` using Vite, React, and TypeScript.
- Add a typed app entrypoint, root shell, account chip, side navigation, and placeholder selected-result workbench.
- Add first-pass CSS variable theme tokens and app styling so theming remains independent from behavior.
- Keep the screen data static and contract-driven until repo-local API adapters are added in a later slice.
- Update roadmap and runbook wiring.

## Non-Goals

- Do not replace the existing Python-rendered `/settings/tenants`, `/search`, `/exports`, or `/logs` pages yet.
- Do not wire the frontend bundle into the Python service in this slice.
- Do not add cross-repo package extraction or publishing.
- Do not add a large component library or routing framework before the first proving surface needs it.
- Do not change API, MCP, CLI, auth, or selected-result JSON contracts.

## Acceptance Criteria

- `frontend/package.json` exposes `dev`, `build`, `preview`, and `typecheck` scripts.
- The frontend app compiles with React and TypeScript.
- The app shell uses semantic theme tokens and neutral operator-console naming.
- The placeholder workbench consumes selected-result contracts from `frontend/src/contracts/`.
- Planning audit and diff checks pass.

## Definition Of Done

- Frontend dependencies install successfully.
- `npm run typecheck` and `npm run build` pass from `frontend/`.
- `git diff --check` passes.
- Planning contract audit passes.

## Completion Notes

- Added the initial Vite/React/TypeScript package under `frontend/`.
- Added `OperatorShell`, `MetricStrip`, theme tokens, app CSS, and a selected-result placeholder workbench.
- Kept the slice static and adapter-free so the next migration can bind live tenant or search APIs without rewriting the shell.
