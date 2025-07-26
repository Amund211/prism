BEGIN;

CREATE TABLE IF NOT EXISTS usernames (
    player_uuid TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    queried_at timestamptz NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_usernames_username_lowercase ON usernames (lower(username));

COMMIT;
