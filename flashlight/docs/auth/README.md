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
   legacy `X-User-Id` path. Once validate succeeds it also tests the verified
   `IdentityKey` against `BLOCKED_USER_IDS` and answers a hit with the
   blocklist middleware's own status and body.
4. The user-id rate limiter (`UserIDKeyFunc`) prefers the context identity and
   falls back to the header.
5. `POST /v1/auth/refresh` bumps `expires_at` / `refresh_until` on **the same
   session id** — no rotation, no proof, **no minimum interval**. `401` means
   the session is finished, re-auth from scratch. `429` is the IP limiters
   only, and they answer ahead of the handler that reads the bearer, so it says
   **nothing about the session** — back off, and don't re-auth on it.

6. Any response to a request that carried a valid bearer gets
   `X-Auth-Refresh: 1` once the session is within `refreshAtOffset` of expiry —
   "refresh now". A hint: a client that ignores it still recovers via 401.
7. The bearer middleware states its verdict in `X-Auth-Session`: `valid` once
   validate succeeded — the blocked-identity 400 included, where the session
   really is fine — `absent` on the no-`Authorization` pass-through, and
   nothing at all on every other arm: a bad session, a malformed header, or a
   `validate` that failed unexpectedly. It is what lets a client attribute a
   401 it did not cause.

Lifetimes, all Go constants in `internal/app/auth_session.go`: `expires_at`
now+**1h**, `refresh_until` now+**2h**, `lifetime_ends_at` stamped at issue as
created_at+**24h** and never extended. **Nothing limits how often a session may
be refreshed** — the endpoint's IP limiters bound the calls, and extra handles
buy no budget because the identity is the rate-limit key. Anonymous logins are
capped at **4** concurrently-active identities per `ip_hash`; the oldest are
soft-revoked as `evicted_by_ip_cap`.

Validate is cached: keyed by session id, **1 minute, successes only**, LRU at
50k entries (`main.go`).

## Signing keys and rotation

`AUTH_CHALLENGE_SIGNING_KEYS` is the HMAC key list for proof-of-work
challenges: a secret, **one per environment** so a staging challenge never
validates against production, newline-delimited base64, at least 32 bytes once
decoded, blank lines and `#` comments ignored (`signing.ParseKeys`).

**The first key signs; every key is accepted.** That is what makes rotation
non-breaking:

1. prepend the new key, deploy;
2. drop the old line once nothing signed with it can still be presented — one
   `challengeTTL` (**60s**) later.

Dropping it in the same deploy instead invalidates every outstanding challenge.
Clients recover by asking for a new one, so the blast radius is a round trip.

Development may run with no keys and generates an ephemeral one at startup, so a
restart invalidates outstanding challenges. Production and staging refuse to
start without keys — deliberately, since a key that dies with the process also
dies on every revision rollout. **An empty secret version is `set`**, so the
check is on the parsed list's length, not on the variable's presence.

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
- **`BLOCKED_USER_IDS` is checked twice, and both are needed.** The blocklist
  middleware tests the `X-User-Id` header, which a blocked caller omits for
  free while presenting a valid session; the bearer middleware tests the
  verified `IdentityKey`. For the anonymous tier `identity_key == userId`, so
  **one entry covers both paths — but only through `NewUserID`**, which
  truncates to **50 chars** while a `userId` may be **100**. Both checks
  normalize, as `UserIDKeyFunc` does; compare a raw key on either side and one
  entry silently covers one path and misses the other. An entry may be dropped
  after **24h**: `lifetime_ends_at` bounds every token that could still be
  presented, so nothing survives it. The cheap header check stays in front — it
  runs before any validation, and no `Authorization` header means no identity
  to test. Two things it is **not**: the auth endpoints test neither list, so a
  blocked identity can still log in and refresh (what it gets is tokens no
  authed handler accepts); and it is not revocation, because dropping the
  bearer and picking a fresh `userId` is a new unauthenticated identity — the
  `X-User-Id` fallback pitfall below, which outlives this.
- **A validate cache hit re-checks nothing.** Expiry is only evaluated inside
  `create()`, so an entry serves for its full minute regardless of what the row
  does. A revoked or expired session stays usable for up to a minute; accepted.
- **Only immutable verdicts may be negatively cached — `expired` rests on the
  refresh invalidation.** Failures are deliberately uncached today. `not_found`
  and `revoked` are permanent and would be safe; **`expired` is not permanent,
  because refresh flips it back to valid**, and refresh presents the same cache
  key. Deleting the entry on refresh is what makes caching it feasible at all:
  without that, the retry after a refresh is served a stale 401 and refreshes
  again — which now succeeds, so the client loops for the whole negative TTL
  instead of re-logging in. The other way out, if negative caching is ever
  wanted, is to make
  **`authRefreshWindow` equal `authSessionTTL`**: past `expires_at` a session is
  then also unrefreshable, `expired` becomes immutable, and caching it is safe.
  The cost is the grace window — a client idle past the TTL always pays a full
  re-login instead of a refresh, which hits reactive clients (rainbow) hardest.
- **`X-Auth-Refresh` must be set before the handler writes, and named in
  `Access-Control-Expose-Headers`.** After `WriteHeader` the header map is
  frozen and setting it is a silent no-op; without the CORS entry a browser
  cannot read it, also silently. `shouldHintRefresh` is the expiry-offset check
  alone; the "never advertise a refresh that would 429" rule it used to carry
  went with the minimum refresh interval.
- **`X-Auth-Session` marks the good case, and only `valid` may be trusted.**
  It exists because `/v1/tags/{uuid}` 401s for a bad Urchin API key while the
  middleware 401s for a bad session, and until this header nothing on the wire
  told them apart. Same slot and the same two mechanics as `X-Auth-Refresh` —
  set before the handler writes, named in `Access-Control-Expose-Headers` — but
  read strictly: **absence never means "the session is fine"**. The blocklist,
  the IP limiters, CORS preflight, `/v1/prestiges/{uuid}`, Cloud Run and a
  stripping proxy all answer without it, so a client that reads absence as "the
  server validated my bearer" latches a verdict it cannot clear.
- **Refresh does not rotate the session id.** A leaked token therefore lives to
  its own `lifetime_ends_at` (≤24h) no matter what the real user does; there is
  no user-driven remediation and no "sign out everywhere".
- **Refresh deletes the session's validate cache entry.** Since the id is
  stable and a hit re-checks nothing, leaving it means every read for the rest
  of that minute — the `X-Auth-Refresh` hint included — sees the pre-refresh
  `expires_at`, so the hint keeps firing on a session already refreshed. The
  delete does not reach a validate already inside `create()`; that one still
  writes its pre-refresh view.
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
