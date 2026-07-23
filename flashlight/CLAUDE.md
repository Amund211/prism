flashlight — the Cloud Run Go backend for the Prism Overlay Project.

## Postgres

Postgres runs on the host, outside the sandbox (localhost:5432, unix socket `/run/postgresql`).
DB tests run outside the sandbox to access this.
