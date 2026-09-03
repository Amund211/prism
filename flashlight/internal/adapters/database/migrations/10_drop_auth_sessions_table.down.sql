-- Recreates the table empty, as migration 9 left it. The rows dropped by the
-- up migration are gone for good; unlike migration 9's down there is no
-- reconciliation to attempt, because no code reads what this restores.
-- Clients recover by logging in again.
CREATE TABLE IF NOT EXISTS auth_sessions (
    id              TEXT PRIMARY KEY,
    identity_type   TEXT NOT NULL,
    identity_key    TEXT NOT NULL,
    ip_hash         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    refresh_until   TIMESTAMPTZ NOT NULL,
    lifetime_ends_at TIMESTAMPTZ NOT NULL,
    last_used_at    TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ,
    revoked_reason  TEXT
);

CREATE INDEX IF NOT EXISTS auth_sessions_active_ip
    ON auth_sessions (identity_type, ip_hash, created_at)
    WHERE revoked_at IS NULL;
