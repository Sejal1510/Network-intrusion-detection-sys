# Continuous Integration

**Status: Milestone 8, GitHub Actions.** Every push and pull request against
`main` runs the same lint/test commands a contributor runs locally — nothing
in CI that isn't also a documented local command, so a red check is always
reproducible on a laptop.

## Why two workflows, not one

`.github/workflows/backend-ci.yml` and `.github/workflows/frontend-ci.yml`
are separate, each path-scoped (`paths:` on `src/**`+`tests/**`+
`pyproject.toml` for the backend, `frontend/**` for the frontend) so a
change to one half of the platform doesn't wait on — or trigger — a runner
for the other. This mirrors the repo's own split: `src/nids` and `frontend/`
already have independent dependency managers (`pyproject.toml` vs.
`package.json`), independent test runners (`pytest` vs. `vitest`), and
independent lint tools (`ruff` vs. `oxlint`); the workflow boundary just
follows that existing line rather than introducing a new one.

## Backend (`backend-ci.yml`)

```bash
pip install -e ".[dev]"
ruff check src tests
pytest -q
```

Lint is scoped to `src` and `tests` — not `.` — because `ruff check .` also
picks up `legacy/`, the pre-rewrite student prototype that predates this
project's lint standard and isn't being incrementally cleaned up; holding
it to the same bar would make CI red for reasons unrelated to the rewrite
this repo is actually tracking.

## Frontend (`frontend-ci.yml`)

```bash
npm ci
npm run lint    # oxlint
npm test        # vitest run
npm run build   # tsc -b && vite build
```

`npm ci` (not `npm install`) installs exactly what `package-lock.json`
pins — the same install a deploy would do — so a lockfile drift that
`npm install` would silently paper over instead fails CI. The build step
doubles as a type-check gate (`tsc -b` before `vite build`), so a type
error fails CI even though nothing here runs `tsc --noEmit` directly.

## What's intentionally not here yet

- **Coverage thresholds / reporting.** Both suites pass today (379 backend,
  29 frontend); enforcing a numeric floor is a future addition once there's
  a baseline worth protecting, not a blocker for CI existing at all.
- **Deployment.** CI ends at a green check — no image build/push, no
  release step. That's packaging/deployment, a separate concern from
  "does this change break anything," and doesn't conflict with adding one
  later as its own job or workflow.
- **Matrix builds.** One Python version (3.12) and one Node version (22) —
  matching local dev, not a support-matrix commitment.
