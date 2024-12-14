package storage

import (
	"context"
	"fmt"
	"log/slog"
	"os"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jmoiron/sqlx"
	"github.com/lib/pq"
	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/processing"
	"github.com/Amund211/flashlight/internal/strutils"
)

func newHypixelAPIPlayer(id int) *processing.HypixelAPIPlayer {
	value := &id
	return &processing.HypixelAPIPlayer{
		Stats: &processing.HypixelAPIStats{
			Bedwars: &processing.HypixelAPIBedwarsStats{
				Kills:        value,
				SoloKills:    value,
				DoublesKills: value,
				ThreesKills:  value,
				FoursKills:   value,
			},
		},
	}
}

func newUUID(t *testing.T) string {
	id, err := uuid.NewRandom()
	require.NoError(t, err)
	return id.String()
}

func newPostgresPersistor(t *testing.T, db *sqlx.DB, schema string) *PostgresStatsPersistor {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))

	db.MustExec(fmt.Sprintf("DROP SCHEMA IF EXISTS %s CASCADE", pq.QuoteIdentifier(schema)))

	migrator := NewDatabaseMigrator(db, logger)

	err := migrator.Migrate(schema)
	require.NoError(t, err)

	return NewPostgresStatsPersistor(db, schema)
}

func TestPostgresStatsPersistor(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping db tests in short mode.")
	}

	ctx := context.Background()
	db, err := NewPostgresDatabase(LOCAL_CONNECTION_STRING)
	require.NoError(t, err)

	now := time.Now()

	t.Run("StoreStats", func(t *testing.T) {
		t.Parallel()
		p := newPostgresPersistor(t, db, "store_stats")

		requireStored := func(t *testing.T, playerUUID string, player *processing.HypixelAPIPlayer, queriedAt time.Time, targetCount int) {
			t.Helper()

			normalizedUUID, err := strutils.NormalizeUUID(playerUUID)
			require.NoError(t, err)

			playerData, err := playerToDataStorage(player)
			require.NoError(t, err)

			txx, err := db.Beginx()
			require.NoError(t, err)
			defer txx.Rollback()

			_, err = txx.ExecContext(ctx, fmt.Sprintf("SET search_path TO %s", pq.QuoteIdentifier("store_stats")))

			row := txx.QueryRowx("SELECT COUNT(*) FROM stats WHERE player_uuid = $1 AND player_data = $2 AND queried_at = $3", normalizedUUID, playerData, queriedAt)
			require.NoError(t, row.Err())

			var count int
			require.NoError(t, row.Scan(&count))
			require.Equal(t, targetCount, count)

			if normalizedUUID != playerUUID {
				row := txx.QueryRowx("SELECT COUNT(*) FROM stats WHERE player_uuid = $1 AND player_data = $2 AND queried_at = $3", playerUUID, playerData, queriedAt)
				require.NoError(t, row.Err())

				var count int
				require.NoError(t, row.Scan(&count))
				require.Equal(t, 0, count, "un-normalized UUID should not be stored")
			}

			err = txx.Commit()
			require.NoError(t, err)
		}

		requireNotStored := func(t *testing.T, playerUUID string, player *processing.HypixelAPIPlayer, queriedAt time.Time) {
			t.Helper()
			requireStored(t, playerUUID, player, queriedAt, 0)
		}

		requireStoredOnce := func(t *testing.T, playerUUID string, player *processing.HypixelAPIPlayer, queriedAt time.Time) {
			t.Helper()
			requireStored(t, playerUUID, player, queriedAt, 1)
		}

		t.Run("store empty object", func(t *testing.T) {
			t.Parallel()

			uuid := newUUID(t)
			player := newHypixelAPIPlayer(0)

			requireNotStored(t, uuid, player, now)
			err := p.StoreStats(ctx, uuid, player, now)
			require.NoError(t, err)
			requireStoredOnce(t, uuid, player, now)
		})

		t.Run("store multiple for same user", func(t *testing.T) {
			t.Parallel()
			player_uuid := newUUID(t)

			player1 := newHypixelAPIPlayer(1)
			t1 := now
			player2 := newHypixelAPIPlayer(2)
			t2 := t1.Add(time.Second)

			requireNotStored(t, player_uuid, player1, t1)
			err := p.StoreStats(ctx, player_uuid, player1, t1)
			require.NoError(t, err)
			requireStoredOnce(t, player_uuid, player1, t1)

			requireNotStored(t, player_uuid, player2, t2)
			err = p.StoreStats(ctx, player_uuid, player2, t2)
			require.NoError(t, err)
			requireStoredOnce(t, player_uuid, player2, t2)

			// We never stored these combinations
			requireNotStored(t, player_uuid, player1, t2)
			requireNotStored(t, player_uuid, player2, t1)
		})

		t.Run("same data for multiple users", func(t *testing.T) {
			t.Parallel()
			uuid1 := newUUID(t)
			uuid2 := newUUID(t)
			player := newHypixelAPIPlayer(3)

			requireNotStored(t, uuid1, player, now)
			err := p.StoreStats(ctx, uuid1, player, now)
			require.NoError(t, err)
			requireStoredOnce(t, uuid1, player, now)

			requireNotStored(t, uuid2, player, now)
			err = p.StoreStats(ctx, uuid2, player, now)
			require.NoError(t, err)
			requireStoredOnce(t, uuid2, player, now)

			requireStoredOnce(t, uuid1, player, now)
		})

		t.Run("duplicate entry for single user", func(t *testing.T) {
			t.Parallel()
			player_uuid := newUUID(t)
			player := newHypixelAPIPlayer(3)

			requireNotStored(t, player_uuid, player, now)
			err := p.StoreStats(ctx, player_uuid, player, now)
			require.NoError(t, err)
			requireStored(t, player_uuid, player, now, 1)

			err = p.StoreStats(ctx, player_uuid, player, now)
			require.NoError(t, err)
			requireStored(t, player_uuid, player, now, 2)
		})

		t.Run("store nil player fails", func(t *testing.T) {
			t.Parallel()
			err := p.StoreStats(ctx, newUUID(t), nil, now)
			require.Error(t, err)
			require.Contains(t, err.Error(), "player is nil")
		})
	})
}
