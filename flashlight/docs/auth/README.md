---
title: Auth sessions — how it works
topic: auth
area: internal/app, internal/ports, internal/authsessiontoken, internal/signing
created_at: 2026-08-08
status: current
tags: [auth, sessions, bearer, proof-of-work, rate-limiting]
---

# Auth sessions

Bearer sessions, so the per-user rate budget keys on an identity we verified
rather than a self-asserted `X-User-Id` header. Only the **anonymous** tier is
built. Rationale lives outside this repo in `auth-plan/`; this file is what runs
plus what breaks silently.

## The shape of it

**The session is the handle** — `flsess_<base64url(payload)>.<base64url(hmac)>`,
signed with `AUTH_SESSION_SIGNING_KEYS` (`internal/authsessiontoken`). There is
no row, no lookup, no cache; validating is a signature check. The payload holds
`typ`, `identityType`, `identityKey`, `issuedAtUnixMillis`,
`lineageIssuedAtUnixMillis`, `lineage`, `generation` — and no deadlines.

- `POST /v1/auth/anonymous/challenge` `{userId}` → a signed, stateless
  proof-of-work challenge bound to that `userId` and the caller's IP. Difficulty
  is **0** today (`proofofwork.DefaultDifficulty`); the mechanism is mandatory so
  the dial can move without a client retrofit.
- `POST /v1/auth/anonymous/login` `{userId, challenge, solution}` → `sessionId`,
  `tier`, and **durations, never timestamps**. The identity is the presented
  `userId`.
- `POST /v1/auth/refresh` re-stamps `issuedAt`, bumps `generation` and seals **a
  new handle**. No proof, no minimum interval. The client must store what comes
  back.
- The bearer middleware (`ports.NewBearerAuthMiddleware`, on nine handlers)
  validates, puts `{SessionID, IdentityType, IdentityKey}` in the context, and
  401s what it cannot validate. **No `Authorization` header at all passes
  through** to the legacy `X-User-Id` path.
- Responses carry `X-Auth-Refresh: 1` within `refreshAtOffset` of expiry (a hint
  — ignoring it still recovers via 401) and `X-Auth-Session` with the
  middleware's verdict.

Lifetimes are **derived, never stamped**. `deadlinesFor`
(`internal/app/auth_session.go`) is the only thing that computes them:

```
lifetimeEndsAt = lineageIssuedAt + 24h        // the chain cap
expiresAt      = min(issuedAt + 1h,  lifetimeEndsAt)
refreshUntil   = min(issuedAt + 2h,  lifetimeEndsAt)
```

`lineage` and `generation` are read by **nothing** today. They are in the payload
on purpose, so an issuance-events table can be added later without a format bump.
They are not dead fields — do not remove them.

## Signing keys and rotation

**Two key lists, never shared.** Domain separation is what stops a challenge blob
and a session handle from being confused for one another; the payload's `typ` is
the other half.

| Variable | Signs | A dropped key costs |
|---|---|---|
| `AUTH_CHALLENGE_SIGNING_KEYS` | proof-of-work challenges | outstanding challenges, ≤ `challengeTTL` (**60s**) |
| `AUTH_SESSION_SIGNING_KEYS` | session handles | **every live session** — a mass logout, up to 24h of chains |

Both are secrets, **one per environment** so a staging blob never validates
against production: newline-delimited base64, ≥32 bytes decoded.

**The first key signs; every key is accepted**, which is what makes rotation
non-breaking: prepend the new key and deploy, then drop the old line once nothing
signed with it can still be presented — 60s for challenges, **24h** for sessions.
Dropping a key in the same deploy is instead a revocation, and the only
irreversible one available.

Development generates an ephemeral key at startup. Production and staging refuse
to boot without keys, since a key that dies with the process also dies on every
revision rollout. **An empty secret version still counts as `set`**, so the check
is on the parsed list's length, not the variable's presence.

## Pitfalls

These are the parts you cannot recover by reading the code.

- **`lineageIssuedAt` is copied on reseal, never re-stamped, and the chain cap is
  derived from it — never from `issuedAt`.** `refreshed()` is the only writer of
  a refreshed session for exactly this reason. Get it wrong and refresh becomes
  an unbounded lifetime extension: invisible until a session has lived a week.
- **Expiry is not monotonic, because nothing is stamped.** Shortening a lifetime
  constant kills live sessions (intended); **lengthening one resurrects dead
  handles**, since deadlines are recomputed per request. A lifetime reduction is
  therefore *not* a revocation — treat it as permanent, or drop a signing key.
- **The blocklist is the only revocation.** No row to mark, so `BLOCKED_USER_IDS`
  plus dropping a key is the whole toolbox. A leaked signing key mints any
  identity in any tier, including tiers that do not exist yet.
- **`BLOCKED_USER_IDS` is checked twice and both are needed** — the blocklist
  middleware on the `X-User-Id` header (which a blocked caller omits for free
  while presenting a valid session) and the bearer middleware on the verified
  `IdentityKey`. One entry covers both paths **only through `NewUserID`**, which
  truncates to **50 chars** while login accepts **100**; compare a raw key on
  either side and one entry silently covers one path and misses the other.
  Nothing in CI pins that pair. Entries may be dropped after 24h, which the chain
  cap bounds.
- **Never key a rate limiter on `session_id`.** One identity may hold any number
  of concurrent sessions, so that hands out a fresh budget per login. The
  identity is the unit — which is also why extra handles buy no budget, and why
  nothing limits how often a session may be refreshed.
- **Nothing bounds how many identities one IP may hold sessions for.**
  `authsessionguard.AllowAll{}` in `main.go` is that decision, made visible. A
  guard that *does* refuse must wrap `domain.ErrAuthSessionIssuanceRefused` —
  that is what login answers with a **429**; anything else is a 500 plus a Sentry
  report.
- **A `429` from refresh says nothing about the session.** Only the IP limiters
  produce it, and they answer ahead of the handler that reads the bearer. Back
  off; do not re-authenticate on it.
- **Only `X-Auth-Session: valid` may be trusted; absence never means "the session
  is fine".** It exists because `/v1/tags/{uuid}` 401s for a bad Urchin API key
  while the middleware 401s for a bad session. The blocklist, the IP limiters,
  CORS preflight, `/v1/prestiges/{uuid}`, Cloud Run and a stripping proxy all
  answer without it, so a client reading absence as "the server validated my
  bearer" latches a verdict it cannot clear.
- **`X-Auth-Refresh` and `X-Auth-Session` must be set before the handler writes,
  and named in `Access-Control-Expose-Headers`.** After `WriteHeader` the header
  map is frozen and setting one is a silent no-op; without the CORS entry a
  browser cannot read it, also silently.
- **Refresh rotates the handle and does not revoke the parent.** The old handle
  validates until its own `expiresAt`, so a client that drops the response still
  works for up to an hour. A leaked handle likewise lives to its own deadline
  (≤24h) whatever the real user does: there is no "sign out everywhere".
- **A handle must never reach a log or an error report.** Nothing does today, and
  the non-obvious reason is `SendDefaultPII` left **false** — that is why
  `sentryhttp` strips `Authorization` from the request attached to every event.
  Turning it on ships bearers to Sentry
  (`TestSentryDoesNotSendTheAuthorizationHeader`).
- **The payload is readable by anyone holding the handle** — signed, not
  encrypted, and AEAD is refused. It carries a `userId` the client generated
  itself, so the disclosure is ~nil; the hazard is that readability invites
  somebody to parse it, and opaque-by-contract is the whole reason this backing
  could be swapped without a client release.
- **The bearer middleware must stay behind an IP limiter and inside CORS, and
  ahead of the identity-keyed limiter**, which needs the identity.
  `TestBearerAuthMiddlewareMountPosition` is the only thing keeping the nine
  hand-assembled chains in agreement.
- **The `X-User-Id` fallback still exists**, so a self-asserted header can be
  aimed at an anonymous identity's bucket. Ends when the fallback does.
- **`pow_challenge_age_seconds` only samples challenges that come back**, so a
  difficulty past what clients can finish makes `outcome="ok"` look *better* as
  the slow half stops reporting. Read it next to `outcome="expired"`.
- **CORS is not observable locally** — `dev` has no backend, the `proxy-*` modes
  are same-origin, tests are mocked. Verify against `flashlight-test` with curl.
