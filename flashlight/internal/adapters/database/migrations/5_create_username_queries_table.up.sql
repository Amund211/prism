CREATE TABLE IF NOT EXISTS username_queries (
    player_uuid TEXT NOT NULL,
    username TEXT NOT NULL,
    last_queried_at timestamptz NOT NULL,
    PRIMARY KEY (player_uuid, username)
);
