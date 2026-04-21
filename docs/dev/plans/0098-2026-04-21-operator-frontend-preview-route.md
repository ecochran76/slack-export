# 0098 | Operator Frontend Preview Route

State: CLOSED

Roadmap: P09

## Current State

- `0097` added a minimal Vite/React/TypeScript frontend package under `frontend/`.
- Before this slice, the built frontend had no authenticated Python-service route and could only be inspected through Vite tooling.
- The Python service now serves the built app at `/operator` and built assets below `/operator/assets/`, protected by the existing frontend-auth guard.

## Scope

- Configure Vite to emit asset URLs under `/operator/`.
- Serve `frontend/dist/app/index.html` through the existing Python API server at `/operator`.
- Serve built frontend assets through `/operator/assets/...` with path traversal protection.
- Keep the route authenticated when frontend auth is enabled.
- Add a test-only override for the frontend dist directory so API tests do not depend on a local build artifact.
- Update roadmap, runbook, and operator-facing docs.

## Non-Goals

- Do not replace `/settings/tenants`, `/search`, `/exports`, `/logs`, or `/runtime/reports`.
- Do not add live API adapters to the React app.
- Do not require the Vite dev server for the managed user-scoped runtime.
- Do not package frontend build artifacts into Python distributions in this slice.
- Do not change API, MCP, CLI, auth-session, or selected-result JSON semantics.

## Acceptance Criteria

- Unauthenticated `/operator` requests redirect to `/login` when frontend auth is enabled.
- Authenticated `/operator` requests serve the built app HTML.
- Authenticated `/operator/assets/...` requests serve built assets and reject missing or unsafe paths.
- Existing Python-rendered operator pages remain unchanged.
- Frontend and targeted API validations pass.

## Definition Of Done

- `npm run build` passes from `frontend/`.
- Targeted API auth test covers `/operator` and `/operator/assets/...`.
- Python compile check for `slack_mirror/service/api.py` passes.
- `git diff --check` passes.
- Planning contract audit passes.

## Completion Notes

- Added Vite `base: "/operator/"`.
- Added authenticated `/operator` and `/operator/assets/...` handling to `slack_mirror/service/api.py`.
- Added `SLACK_MIRROR_OPERATOR_FRONTEND_DIST` as a narrow test/runtime override for the built frontend root.
- Left all existing Python-rendered pages active while the React app remains a preview surface.
