DROP INDEX IF EXISTS auth_sessions_active_ip;

CREATE INDEX IF NOT EXISTS auth_sessions_ip_hash
    ON auth_sessions (ip_hash);

-- Restoring the partial unique index needs at most one active row per
-- identity, and the up migration makes multiple the normal case — every
-- second login produces one. Without this reconciliation the CREATE
-- below fails on duplicates and golang-migrate leaves the schema dirty
-- with the rollback half-applied, so there is no usable `down` at all.
--
-- Keep the newest session per identity and soft-revoke the rest as
-- 'replaced', which is exactly what the Create being restored would
-- have done to them (last writer wins). Tie-broken on id so the choice
-- is deterministic. This destroys live sessions, so it is a real cost of
-- rolling back rather than a free undo — but an arbitrary-and-defined
-- winner beats a migration that cannot run.
UPDATE auth_sessions
   SET revoked_at = now(),
       revoked_reason = 'replaced'
 WHERE revoked_at IS NULL
   AND id NOT IN (
       SELECT DISTINCT ON (identity_type, identity_key) id
         FROM auth_sessions
        WHERE revoked_at IS NULL
        ORDER BY identity_type, identity_key, created_at DESC, id DESC
   );

CREATE UNIQUE INDEX IF NOT EXISTS auth_sessions_active_identity
    ON auth_sessions (identity_type, identity_key)
    WHERE revoked_at IS NULL;
