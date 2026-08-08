"""
Auth sessions for the flashlight API

Flashlight issues short-lived opaque bearer sessions so that our per-user rate
budget keys on an identity it has verified, rather than on the self-asserted
`X-User-Id` header. Prism holds exactly one session for the whole process and
sends it on every flashlight request.

The pieces:

- `session`         the `Session` value object and the login/refresh response parser
- `proof_of_work`   the hash puzzle every anonymous login must solve
- `endpoints`       the three HTTP calls (challenge, login, refresh)
- `anonymous`       the anonymous tier's `LoginMethod`
- `manager`         `AuthManager`, which owns the session and the auth thread
- `request`         `send_authenticated`, used by every flashlight call site

Only `anonymous` knows which tier we are on. Everything else works off a
`Session` alone, so a second tier (Microsoft) is a second `LoginMethod` and
nothing more.
"""
