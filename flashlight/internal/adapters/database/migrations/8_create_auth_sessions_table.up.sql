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

CREATE UNIQUE INDEX IF NOT EXISTS auth_sessions_active_identity
    ON auth_sessions (identity_type, identity_key)
    WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS auth_sessions_ip_hash
    ON auth_sessions (ip_hash);
