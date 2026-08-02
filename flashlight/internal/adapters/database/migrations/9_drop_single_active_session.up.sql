-- Drop single-active-session. An identity may now hold any number of
-- concurrent active sessions; duplicates coexist and expire naturally.
DROP INDEX IF EXISTS auth_sessions_active_identity;

-- auth_sessions_ip_hash covered revoked rows and only the one column,
-- while EnforceActiveIPCap — the only query touching ip_hash — also
-- filters on identity_type, revoked_at and refresh_until. It handed back
-- every row ever recorded for an ip_hash and filtered afterwards, so with
-- nothing deleting rows each login from a given IP was slower than the
-- last. Replace it with one that matches the query.
DROP INDEX IF EXISTS auth_sessions_ip_hash;

CREATE INDEX IF NOT EXISTS auth_sessions_active_ip
    ON auth_sessions (identity_type, ip_hash, created_at)
    WHERE revoked_at IS NULL;
