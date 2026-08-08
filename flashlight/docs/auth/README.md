---
title: Auth sessions — how it works
topic: auth
area: internal/app, internal/ports, internal/adapters/authsessionrepository
created_at: 2026-08-08
status: current
tags: [auth, sessions, bearer, proof-of-work, rate-limiting]
---

# Auth sessions

Server-issued opaque bearer sessions, so the per-user rate budget keys on an
identity flashlight verified instead of a self-asserted `X-User-Id` header.
Two tiers were designed; only **anonymous** exists. Design rationale lives
outside this repo in `auth-plan/`; this file is the short version of what is
actually running.

## The flow

1. `POST /v1/auth/anonymous/challenge` `{userId}` → a signed, stateless
   proof-of-work challenge bound to that `userId` and the caller's IP. No DB,
   no server state. Difficulty is **0** today (`proofofwork.DefaultDifficulty`):
   the mechanism is mandatory, the work is zero, so the dial can be turned
   without a client retrofit.
2. `POST /v1/auth/anonymous/login` `{userId, challenge, solution}` → inserts an
   `auth_sessions` row and returns `sessionId` (`flsess_` + 32 random bytes),
   `tier`, and **durations** (never timestamps), so no client depends on a
   wall clock. The `identity_key` is the presented `userId`.
3. The client sends `Authorization: Bearer flsess_…`. The bearer middleware
   (`ports.NewBearerAuthMiddleware`, mounted on nine handlers) validates it,
   puts `{SessionID, IdentityType, IdentityKey}` in the request context, and
   401s a header it can't validate. No header at all passes through to the
   legacy `X-User-Id` path.
4. The user-id rate limiter (`UserIDKeyFunc`) prefers the context identity and
   falls back to the header.
5. `POST /v1/auth/refresh` bumps `expires_at` / `refresh_until` on **the same
   session id** — no rotation, no proof required. `401` means the session is
   finished, re-auth from scratch. `429` means too soon (or the IP limit): the
   session is untouched, keep using it and do **not** re-auth.

6. Any response to a request that carried a valid bearer gets
   `X-Auth-Refresh: 1` once the session is within `refreshAtOffset` of expiry —
   "refresh now". A hint: a client that ignores it still recovers via 401.

Lifetimes, all Go constants in `internal/app/auth_session.go`: `expires_at`
now+**1h**, `refresh_until` now+**2h**, `lifetime_ends_at` stamped at issue as
created_at+**24h** and never extended, and at least **30min** must burn between
refreshes. Anonymous logins are capped at **4** concurrently-active identities
per `ip_hash`; the oldest are soft-revoked as `evicted_by_ip_cap`.

Validate is cached: keyed by session id, **1 minute, successes only**, LRU at
50k entries (`main.go`).

## Assumptions and pitfalls

- **Never key a rate limiter on `session_id`.** One identity may hold any
  number of concurrent sessions; keying on the session would hand out a fresh
  budget per login. The identity is the unit.
- **The bearer middleware must stay behind an IP limiter and inside CORS, and
  ahead of the identity-keyed limiter.** Failed validations are uncached
  `SELECT … FOR UPDATE` transactions, so a garbage token in front of the
  limiters is connection-pool exhaustion from one host — this was a live DoS.
  `TestBearerAuthMiddlewareMountPosition` is the only thing keeping the nine
  hand-assembled chains in agreement.
- **A validate cache hit re-checks nothing.** Expiry is only evaluated inside
  `create()`, so an entry serves for its full minute regardless of what the row
  does. A revoked or expired session stays usable for up to a minute; accepted.
- **Only immutable verdicts may be negatively cached — so `expired` may not
  be.** Failures are deliberately uncached today. `not_found` and `revoked` are
  permanent and would be safe; **`expired` is not, because refresh flips it back
  to valid.** Since refresh does not rotate the id, the retry after a refresh
  presents the same cache key: it would be served a stale 401, react by
  refreshing again, and get a `429` (the 30-minute interval), which is not a
  401 and so does not trigger re-login — the client is wedged for the whole
  negative TTL. The alternative, if negative caching is ever wanted, is to make
  **`authRefreshWindow` equal `authSessionTTL`**: past `expires_at` a session is
  then also unrefreshable, `expired` becomes immutable, and caching it is safe.
  The cost is the grace window — a client idle past the TTL always pays a full
  re-login instead of a refresh, which hits reactive clients (rainbow) hardest.
- **`X-Auth-Refresh` must be set before the handler writes, and named in
  `Access-Control-Expose-Headers`.** After `WriteHeader` the header map is
  frozen and setting it is a silent no-op; without the CORS entry a browser
  cannot read it, also silently. Never advertise a refresh that would 429 —
  `shouldHintRefresh` checks `app.RefreshTooSoon` for that reason.
- **Refresh does not rotate the session id.** A leaked token therefore lives to
  its own `lifetime_ends_at` (≤24h) no matter what the real user does; there is
  no user-driven remediation and no "sign out everywhere".
- **Refresh does not invalidate the validate cache.** Harmless only because
  hits aren't re-checked and the id is stable — don't build on it.
- **Concurrent validates of one dead session queue ~50ms apart**, one DB
  round-trip each, because failures release the cache claim instead of
  populating it. Clients that fan out must start recovery from the *first* 401.
- **The `X-User-Id` fallback still exists**, so a self-asserted header can be
  aimed at an anonymous identity's bucket. Ends when the fallback does.
- **Nothing deletes `auth_sessions` rows.** Retention is unbuilt, and it is the
  gate before prism ships auth.
- **`pow_challenge_age_seconds` only samples challenges that come back**, so a
  difficulty past what clients can finish makes `outcome="ok"` look *better* as
  the slow half stops reporting. Read it next to `outcome="expired"`.
- **CORS is not observable locally** — `dev` has no backend, the `proxy-*` modes
  are same-origin, tests are mocked. Verify against `flashlight-test` with curl.
