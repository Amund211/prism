-- The Microsoft tier's long-lived recovery credentials: rainbow's fl_rm
-- cookie and prism's stored credential. Only a hash of the value is kept.
CREATE TABLE IF NOT EXISTS user_credentials (
    credential_hash BYTEA PRIMARY KEY,
    identity_key    TEXT NOT NULL,
    client_type     TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL,
    expires_at      TIMESTAMPTZ NOT NULL,
    last_used_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS user_credentials_identity_key ON user_credentials (identity_key);
