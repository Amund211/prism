package storage_test

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

	"github.com/Amund211/flashlight/internal/storage"
	"github.com/Amund211/flashlight/internal/strutils"
)

func newUUID(t *testing.T) string {
	id, err := uuid.NewRandom()
	require.NoError(t, err)
	return id.String()
}

func newPostgresPersistor(t *testing.T, db *sqlx.DB, schema string) *storage.PostgresStatsPersistor {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))

	db.MustExec(fmt.Sprintf("DROP SCHEMA IF EXISTS %s CASCADE", pq.QuoteIdentifier(schema)))

	migrator := storage.NewDatabaseMigrator(db, logger)

	err := migrator.Migrate(schema)
	require.NoError(t, err)

	return storage.NewPostgresStatsPersistor(db, schema)
}

func TestPostgresStatsPersistor(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping db tests in short mode.")
	}

	ctx := context.Background()
	db, err := storage.NewPostgresDatabase(storage.LOCAL_CONNECTION_STRING)
	require.NoError(t, err)

	now := time.Now()

	t.Run("StoreStats", func(t *testing.T) {
		t.Parallel()
		p := newPostgresPersistor(t, db, "store_stats")

		requireStored := func(t *testing.T, playerUUID string, playerData []byte, queriedAt time.Time, targetCount int) {
			t.Helper()

			normalizedUUID, err := strutils.NormalizeUUID(playerUUID)
			require.NoError(t, err)

			txx, err := db.Beginx()
			require.NoError(t, err)

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
		}

		requireNotStored := func(t *testing.T, playerUUID string, playerData []byte, queriedAt time.Time) {
			t.Helper()
			requireStored(t, playerUUID, playerData, queriedAt, 0)
		}

		requireStoredOnce := func(t *testing.T, playerUUID string, playerData []byte, queriedAt time.Time) {
			t.Helper()
			requireStored(t, playerUUID, playerData, queriedAt, 1)
		}

		t.Run("store empty object", func(t *testing.T) {
			t.Parallel()
			uuid := newUUID(t)
			requireNotStored(t, uuid, []byte("{}"), now)
			err := p.StoreStats(ctx, uuid, []byte("{}"), now)
			require.NoError(t, err)
			requireStoredOnce(t, uuid, []byte("{}"), now)
		})

		t.Run("store multiple for same user", func(t *testing.T) {
			t.Parallel()
			player_uuid := newUUID(t)

			data1 := []byte(`{"seq":1}`)
			t1 := now
			data2 := []byte(`{"seq":2}`)
			t2 := t1.Add(time.Second)

			requireNotStored(t, player_uuid, data1, t1)
			err := p.StoreStats(ctx, player_uuid, data1, t1)
			require.NoError(t, err)
			requireStoredOnce(t, player_uuid, data1, t1)

			requireNotStored(t, player_uuid, data2, t2)
			err = p.StoreStats(ctx, player_uuid, data2, t2)
			require.NoError(t, err)
			requireStoredOnce(t, player_uuid, data2, t2)

			// We never stored these combinations
			requireNotStored(t, player_uuid, data1, t2)
			requireNotStored(t, player_uuid, data2, t1)
		})

		t.Run("same data for multiple users", func(t *testing.T) {
			t.Parallel()
			uuid1 := newUUID(t)
			uuid2 := newUUID(t)
			data := []byte(`{"seq":1}`)

			requireNotStored(t, uuid1, data, now)
			err := p.StoreStats(ctx, uuid1, data, now)
			require.NoError(t, err)
			requireStoredOnce(t, uuid1, data, now)

			requireNotStored(t, uuid2, data, now)
			err = p.StoreStats(ctx, uuid2, data, now)
			require.NoError(t, err)
			requireStoredOnce(t, uuid2, data, now)

			requireStoredOnce(t, uuid1, data, now)
		})

		t.Run("duplicate entry for single user", func(t *testing.T) {
			t.Parallel()
			player_uuid := newUUID(t)
			data := []byte(`{"seq":1}`)

			requireNotStored(t, player_uuid, data, now)
			err := p.StoreStats(ctx, player_uuid, data, now)
			require.NoError(t, err)
			requireStored(t, player_uuid, data, now, 1)

			err = p.StoreStats(ctx, player_uuid, data, now)
			require.NoError(t, err)
			requireStored(t, player_uuid, data, now, 2)
		})

		t.Run("store invalid json fails", func(t *testing.T) {
			t.Parallel()
			err := p.StoreStats(ctx, newUUID(t), []byte("invalid json"), now)
			require.Error(t, err)
			require.Contains(t, err.Error(), "failed to insert stats")
		})
	})
}
