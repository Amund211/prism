flashlight — the Cloud Run Go backend for the Prism Overlay Project.

## Auth

When working on anything auth-related — sessions, the bearer middleware,
proof-of-work, session lifetimes or the validate cache — consult
[docs/auth/README.md](docs/auth/README.md) first. It describes how auth works
today and lists the assumptions and pitfalls that are easy to break silently.
**Keep it updated** when shipped behavior changes, and keep it short: bare
minimum, only the most important things.

## Postgres

Postgres runs on the host, outside the sandbox (localhost:5432, unix socket `/run/postgresql`).
DB tests run outside the sandbox to access this.
