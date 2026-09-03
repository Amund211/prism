---
title: Auth sessions — how it works
topic: auth
area: internal/app, internal/ports, internal/authsessiontoken
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
2. `POST /v1/auth/anonymous/login` `{userId, challenge, solution}` → returns
   `sessionId`, `tier`, and **durations** (never timestamps), so no client
   depends on a wall clock. The identity is the presented `userId`. **No DB and
   no server state:** the session *is* the handle,
   `flsess_<base64url(payload)>.<base64url(hmac-sha256)>`, signed with
   `AUTH_SESSION_SIGNING_KEYS` (`internal/authsessiontoken`). The payload holds
   `typ`, `identityType`, `identityKey`, `issuedAtUnixMillis`,
   `lineageIssuedAtUnixMillis`, `lineage` and `generation` — and no deadlines.
   Validating is a signature check; nothing is looked up and nothing is cached.
3. The client sends `Authorization: Bearer flsess_…`. The bearer middleware
   (`ports.NewBearerAuthMiddleware`, mounted on nine handlers) validates it,
   puts `{SessionID, IdentityType, IdentityKey}` in the request context, and
   401s a header it can't validate. No header at all passes through to the
   legacy `X-User-Id` path. Once validate succeeds it also tests the verified
   `IdentityKey` against `BLOCKED_USER_IDS` and answers a hit with the
   blocklist middleware's own status and body.
4. The user-id rate limiter (`UserIDKeyFunc`) prefers the context identity and
   falls back to the header.
5. `POST /v1/auth/refresh` unseals, re-stamps `issuedAt`, bumps `generation`
   and seals **a new handle** — no proof, **no minimum interval**. The client
   must store what comes back; the previous handle is not revoked and keeps
   working until its own expiry. `401` means the session is finished, re-auth
   from scratch. `429` is the IP limiters only, and they answer ahead of the
   handler that reads the bearer, so it says **nothing about the session** —
   back off, and don't re-auth on it.

6. Any response to a request that carried a valid bearer gets
   `X-Auth-Refresh: 1` once the session is within `refreshAtOffset` of expiry —
   "refresh now". A hint: a client that ignores it still recovers via 401.
7. The bearer middleware states its verdict in `X-Auth-Session`: `valid` once
   validate succeeded — the blocked-identity 400 included, where the session
   really is fine — `absent` on the no-`Authorization` pass-through, and
   nothing at all on every other arm: a bad session, a malformed header, or a
   `validate` that failed unexpectedly. It is what lets a client attribute a
   401 it did not cause.

Lifetimes are **derived, never stamped** — `deadlinesFor` in
`internal/app/auth_session.go` is the only thing that computes them, from the
two origins in the payload and the per-tier constants there:

```
lifetimeEndsAt = lineageIssuedAt + 24h        // the chain cap
expiresAt      = min(issuedAt + 1h,  lifetimeEndsAt)
refreshUntil   = min(issuedAt + 2h,  lifetimeEndsAt)
```

`lineageIssuedAt` is the chain's origin — copied by every reseal — and
`issuedAt` is this handle's, re-stamped by every reseal. **Nothing limits how
often a session may be refreshed**: the endpoint's IP limiters bound the calls,
and extra handles buy no budget because the identity is the rate-limit key.

`lineage` and `generation` are recorded by **nothing** today. They are in the
payload on purpose, so an issuance-events table can be built later without a
format bump — they are not dead fields.

## Signing keys and rotation

**Two separate key lists, and they must never be shared.** Domain separation is
what stops a challenge blob and a session handle — two signed blobs differing
only by shape — from being confused for one another; the `typ` field inside the
payload is the second half of it.

| Variable | Signs | A dropped key costs |
|---|---|---|
| `AUTH_CHALLENGE_SIGNING_KEYS` | proof-of-work challenges | outstanding challenges, ≤ `challengeTTL` (**60s**) |
| `AUTH_SESSION_SIGNING_KEYS` | session handles | **every live session** — a mass logout, up to 24h of chains |

Both are secrets, **one per environment** so a staging blob never validates
against production, newline-delimited base64, at least 32 bytes once decoded.
Blank lines and `#` comments are stripped when the env var is read
(`config.lookupNewlineDelimitedEnv`); `signing.ParseKeys` then decodes and
length-checks what survives.

**The first key signs; every key is accepted.** That is what makes rotation
non-breaking:

1. prepend the new key, deploy;
2. drop the old line once nothing signed with it can still be presented — one
   `challengeTTL` (60s) for challenges, **24h** for sessions.

Dropping a key in the same deploy instead is a revocation, and it is the only
irreversible one available: for challenges the blast radius is a round trip,
for sessions it is a silent re-login for everybody.

Development may run with no keys and generates an ephemeral one at startup, so a
restart invalidates outstanding challenges and logs out local sessions.
Production and staging refuse to start without keys — deliberately, since a key
that dies with the process also dies on every revision rollout. **An empty
secret version is `set`**, so the check is on the parsed list's length, not on
the variable's presence.

## Assumptions and pitfalls

- **Never key a rate limiter on `session_id`.** One identity may hold any
  number of concurrent sessions; keying on the session would hand out a fresh
  budget per login. The identity is the unit.
- **Nothing bounds how many identities one IP may hold sessions for.**
  `authsessionguard.AllowAll{}` in `main.go` is that decision, made visible;
  anonymous issuance is bounded only by proof-of-work (difficulty 0 today) and
  the login endpoint's per-IP limiters. The per-IP identity cap that used to
  soft-revoke the oldest identities is gone — it could only count rows, which
  stateless sessions are not, and it bounded concurrently *active* identities
  rather than issuance. `revoked_at` / `revoked_reason` are therefore written
  by nothing. A guard that *does* refuse must wrap
  `domain.ErrAuthSessionIssuanceRefused`: that is what login answers with a
  **429**, and anything else it returns is a 500 plus a Sentry report.
- **The bearer middleware must stay behind an IP limiter and inside CORS, and
  ahead of the identity-keyed limiter.** The order's original motivation is
  gone — a failed unseal is an HMAC, not an uncached `SELECT … FOR UPDATE`
  against 16 connections, which was a live DoS — but keep the order anyway: it
  costs nothing and the identity-keyed limiter needs the identity.
  `TestBearerAuthMiddlewareMountPosition` is the only thing keeping the nine
  hand-assembled chains in agreement.
- **`lineageIssuedAt` is copied on reseal and never re-stamped, and the chain
  cap is derived from it — never from `issuedAt`.** `refreshed()` is the only
  writer of a refreshed session for exactly this reason. Get it wrong and
  refresh becomes an unbounded lifetime extension: silent, and invisible until
  a session has lived a week.
- **Expiry is not monotonic, because nothing is stamped.** Shortening a
  lifetime constant kills live sessions (intended); **lengthening one
  resurrects dead handles**, since every deadline is recomputed from the
  payload on each request. So a lifetime reduction is *not* a revocation —
  treat it as permanent, or drop a signing key, which is the only irreversible
  lever.
- **The payload is readable by anyone holding the handle** — it is signed, not
  encrypted. It carries the `userId` the client generated itself, so the
  disclosure is ~nil; the hazard is that its readability invites somebody to
  parse it. Opaque by contract is the whole reason this backing could change
  without a client release.
- **A leaked signing key mints any identity in any tier**, including tiers that
  do not exist yet. Bounded only by rotation, which is a deploy.
- **The blocklist is the only revocation.** There is no row to mark, so
  `BLOCKED_USER_IDS` on the verified `IdentityKey` (below) plus dropping a
  signing key is the whole toolbox.
- **`BLOCKED_USER_IDS` is checked twice, and both are needed.** The blocklist
  middleware tests the `X-User-Id` header, which a blocked caller omits for
  free while presenting a valid session; the bearer middleware tests the
  verified `IdentityKey`. For the anonymous tier `identity_key == userId`, so
  **one entry covers both paths — but only through `NewUserID`**, which
  truncates to **50 chars** while a `userId` may be **100**. Both checks
  normalize, as `UserIDKeyFunc` does; compare a raw key on either side and one
  entry silently covers one path and misses the other. An entry may be dropped
  after **24h**: the chain cap bounds every handle that could still be
  presented, so nothing survives it. The cheap header check stays in front — it
  runs before any validation, and no `Authorization` header means no identity
  to test. Two things it is **not**: the auth endpoints test neither list, so a
  blocked identity can still log in and refresh (what it gets is tokens no
  authed handler accepts); and it is not revocation, because dropping the
  bearer and picking a fresh `userId` is a new unauthenticated identity — the
  `X-User-Id` fallback pitfall below, which outlives this.
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
- **Refresh rotates the handle, and refreshing does not revoke the parent.**
  The old handle keeps validating until its own `expiresAt`, so a client that
  drops the response still works for up to an hour. A leaked handle likewise
  lives to its own deadline (≤24h) whatever the real user does: there is no
  user-driven remediation and no "sign out everywhere".
- **The `X-User-Id` fallback still exists**, so a self-asserted header can be
  aimed at an anonymous identity's bucket. Ends when the fallback does.
- **`pow_challenge_age_seconds` only samples challenges that come back**, so a
  difficulty past what clients can finish makes `outcome="ok"` look *better* as
  the slow half stops reporting. Read it next to `outcome="expired"`.
- **CORS is not observable locally** — `dev` has no backend, the `proxy-*` modes
  are same-origin, tests are mocked. Verify against `flashlight-test` with curl.
