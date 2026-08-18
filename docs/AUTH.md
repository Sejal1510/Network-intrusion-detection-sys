# Auth, CORS, and CSP model

**Status: Milestone 15 — Security Hardening & Supply-Chain Security.**
This is the doc `nids.api.user_auth`'s module docstring has referenced
since Milestone 11 but that never actually existed until now — this
milestone is also what made it worth writing: `/ws/live` used to
authenticate with a non-expiring device credential (a stand-in from
before real dashboard login existed), which this milestone replaced with
a session-backed ticket. The full audit and decision record that led
here is in this session's conversation history; this doc is the lasting
reference.

## Two identities, never interchangeable

| | Dashboard user | Capture agent device |
|---|---|---|
| Proves | "I'm a logged-in analyst/admin" | "I'm a paired capture agent" |
| Issued by | `POST /auth/login` (bcrypt password check) | `POST /agent/pair` + `/agent/pair/exchange` |
| Lifetime | 8 hours (`session_ttl_seconds`), revocable on logout | Indefinite, revocable via `POST /devices/{id}/revoke` |
| Storage | `sessions` table, only a SHA-256 hash | `devices` table, only a SHA-256 hash |
| Used on | `/auth/*`, `/history/*`, `/devices*`, `/metrics/summary`, `/rules`, `/auth/ws-ticket` | `/agent/ingest` only |

These are deliberately separate credential types (`nids.api.user_auth` vs
`nids.api.agent_auth`), not one "bearer token" concept — a browser
operator proving who they are is a different problem from a capture
agent (a separate, possibly headless, possibly long-unattended process)
proving which machine it is. `tests/test_api_broadcast.py`'s
`test_live_rejects_a_device_credential` exists specifically to keep them
from silently becoming interchangeable again.

## Every authenticated surface, including `/ws/live`, resolves to one of these

REST routes attach the dashboard session as a normal `Authorization:
Bearer <token>` header (`frontend/src/api/client.ts`), checked by
`nids.api.auth._get_current_user` / `authenticate_session`. That's the
only mechanism for every login-gated route except one:

**`/ws/live`** can't use that header — browsers don't let `WebSocket`
set custom handshake headers, which is *why* this project used to fall
back to a `?token=` query parameter carrying a **device** credential
(the only bearer-token concept that existed before Milestone 11 added
real dashboard login). That fallback quietly outlived its original
reason: once real sessions existed, `/ws/live` kept trusting a
credential type meant for an unattended capture agent, with no
expiry, no tie to who was actually logged in, and a token sitting in
the URL indefinitely.

The fix (`nids.api.broadcast`, `nids.api.user_auth.issue_ws_ticket`/
`verify_ws_ticket`): `POST /auth/ws-ticket`, itself gated by the same
`CurrentUserDep` every other route uses, mints a **stateless,
~60-second-lived ticket** embedding only a user id (`itsdangerous`,
mirroring `nids.api.agent_auth`'s pairing-token pattern, different salt
so the two token *shapes* can never be swapped even though they may
share the same `secret_key`). `useLiveFeed` mints one immediately before
every connect and reconnect and passes it as `/ws/live?ticket=`.

Consequences worth being explicit about:
- A revoked/expired dashboard session can't mint a new ticket, so
  reconnect attempts fail closed within one backoff cycle.
- An already-open `/ws/live` connection isn't forcibly severed the
  instant a session is revoked (no per-message reauth, same as every
  other long-lived connection in this codebase) — but logging out flips
  `useUserAuth`'s `status` to `"anonymous"`, which makes `RequireAuth`
  redirect immediately, unmounting whatever page held the connection and
  running `useLiveFeed`'s cleanup. No separate "kill the socket on
  logout" code was needed for this reason.
- Whatever value does land in a proxy/access log via the query string is
  a single-purpose, ~60-second-lived ticket, not the real session token
  and not a non-expiring device credential — a fundamentally smaller
  window than what existed before this milestone.
- Not fully single-use: `verify_ws_ticket` checks signature + TTL only,
  no server-side "already redeemed" tracking. Accepted deliberately, the
  same stateless tradeoff `nids.api.agent_auth`'s pairing tokens already
  make — replay is bounded to the ~60-second window, and adding a
  redemption store would be real complexity for a marginal reduction of
  an already-small risk.

## CORS

No `CORSMiddleware` is installed unless `--cors-origin` is passed
(`nids.api.config.ServingConfig.cors_origins`, empty by default) — see
`docs/API.md`'s "CORS" section for the flag itself.
`allow_credentials` stays off unconditionally: every authenticated
request (REST bearer header, or the `/ws/live` ticket above) is attached
explicitly by client code, never sent automatically by the browser the
way a cookie would be — so there's no ambient credential for
credentialed CORS to protect, and enabling it would only widen the
attack surface for no behavioral gain.

## CSP and security headers

Two separate places, because they're two separate kinds of response:

- **Backend (`nids.api.security_headers.SecurityHeadersMiddleware`)** —
  this API returns JSON only, so its policy is maximally strict:
  `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'`,
  `Referrer-Policy: no-referrer` (a URL can carry a ws-ticket — see
  above — so it should never leak via a cross-origin `Referer` either),
  `Permissions-Policy` disabling camera/mic/geolocation. Applied to
  every response, including error responses, via `setdefault` so it
  never clobbers a header a route set on purpose.
- **Frontend (`frontend/nginx.conf.template`)** — this *does* serve
  HTML/JS, so its CSP is more involved:
  - `script-src 'self'`, no `'unsafe-inline'`. The one script this SPA
    needs to run before first paint (a pre-paint theme application, to
    avoid a flash of the wrong theme) is `public/theme-init.js` — a
    same-origin external file, not an inline `<script>` in `index.html`
    as it used to be, specifically so it doesn't need a CSP hash
    allowance that would silently go stale the next time someone edits
    it.
  - `style-src 'self' 'unsafe-inline'` — kept permissive on purpose.
    React and Recharts both set inline `style="..."` attributes at
    render time; auditing every component to eliminate that would be
    real effort for a much narrower payoff than `script-src`, since
    inline *style* injection is a far smaller attack surface than inline
    *script* injection (no arbitrary code execution, at most cosmetic/
    exfiltration-via-CSS tricks). A fully strict `style-src` is a
    reasonable future tightening, not done in this milestone.
  - `connect-src 'self' ${BACKEND_HTTP_ORIGIN} ${BACKEND_WS_ORIGIN}` —
    the two placeholders are resolved at **container start**, not build
    time, via nginx's built-in `envsubst`-on-`*.template` mechanism
    (`docker-entrypoint.d/20-envsubst-on-templates.sh`, already in the
    base image — no extra tooling). `docker-compose.yml` sets
    `BACKEND_HTTP_ORIGIN` from the same `VITE_API_BASE_URL` value the JS
    bundle itself was built against (so they can't drift for the common
    case) and `BACKEND_WS_ORIGIN` as its own setting, since a ws(s)://
    origin has no build-arg equivalent to mirror. Deploying anywhere
    other than the default `docker-compose up` topology means setting
    both to match wherever the backend actually is.
  - `object-src 'none'`, `base-uri 'self'`, `frame-ancestors 'none'`,
    plus the same `X-Content-Type-Options`/`Referrer-Policy`/
    `Permissions-Policy` headers as the backend.

  This is templated rather than a static file specifically because a
  hardcoded `connect-src` would either be wrong for every deployment
  that isn't the default `localhost:8000`, or require editing the
  checked-in config file per deployment — the same "explicit, no silent
  wrong defaults" philosophy `ServingConfig.cors_origins` already uses.

## What's still a known, accepted limitation

- Session tokens live in `localStorage` (`useUserAuth.ts`), not an
  `HttpOnly` cookie — chosen because it composes cleanly with
  `allow_credentials=False` CORS and needs no CSRF defense, at the cost
  of being readable by any script that runs on the page. The backend's
  strict CSP and the frontend's `script-src 'self'` (no inline, no
  `unsafe-eval`) are this project's mitigation for that tradeoff, not a
  claim that the tradeoff doesn't exist.
- No account lockout beyond per-IP rate limiting on `/auth/login`
  (`auth_rate_limit_per_minute`) — a distributed attacker rotating IPs
  isn't stopped by this alone.
- Device credentials still don't expire (by design — a capture agent is
  meant to run unattended for weeks; see `nids.api.config`). Only
  revocation via the Devices page closes a compromised one.
