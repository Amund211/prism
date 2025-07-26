BEGIN;
CREATE TABLE IF NOT EXISTS stats (
    id TEXT PRIMARY KEY,
    player_uuid TEXT NOT NULL,
    queried_at timestamptz NOT NULL,
    player_data JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_stats_player_uuid ON stats (player_uuid);
CREATE INDEX IF NOT EXISTS idx_queried_at_uuid ON stats (queried_at);

CREATE INDEX IF NOT EXISTS idx_stats_player_uuid_and_queried_at ON stats (player_uuid, queried_at);
COMMIT;
