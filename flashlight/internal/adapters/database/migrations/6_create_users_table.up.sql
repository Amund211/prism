CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    first_seen_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    seen_count BIGINT NOT NULL DEFAULT 1
);
