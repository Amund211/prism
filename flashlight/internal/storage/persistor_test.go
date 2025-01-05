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
		SCHEMA_NAME := "store_stats"
		t.Parallel()
		p := newPostgresPersistor(t, db, SCHEMA_NAME)

		requireStored := func(t *testing.T, playerUUID string, player *processing.HypixelAPIPlayer, queriedAt time.Time, targetCount int) {
			t.Helper()

			normalizedUUID, err := strutils.NormalizeUUID(playerUUID)
			require.NoError(t, err)

			playerData, err := playerToDataStorage(player)
			require.NoError(t, err)

			txx, err := db.Beginx()
			require.NoError(t, err)
			defer txx.Rollback()

			_, err = txx.ExecContext(ctx, fmt.Sprintf("SET search_path TO %s", pq.QuoteIdentifier(SCHEMA_NAME)))

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
			t2 := t1.Add(3 * time.Minute)

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

		t.Run("stats are not stored within one minute", func(t *testing.T) {
			t.Parallel()
			player_uuid := newUUID(t)

			player1 := newHypixelAPIPlayer(1)
			t1 := now

			requireNotStored(t, player_uuid, player1, t1)
			err := p.StoreStats(ctx, player_uuid, player1, t1)
			require.NoError(t, err)
			requireStoredOnce(t, player_uuid, player1, t1)

			player2 := newHypixelAPIPlayer(2)
			for i := 0; i < 60; i++ {
				t2 := t1.Add(time.Duration(i) * time.Second)

				requireNotStored(t, player_uuid, player2, t2)
				err = p.StoreStats(ctx, player_uuid, player2, t2)
				require.NoError(t, err)
				requireNotStored(t, player_uuid, player2, t2)
			}
		})

		t.Run("consecutive duplicate stats are not stored", func(t *testing.T) {
			t.Parallel()
			player_uuid := newUUID(t)

			playerdata := newHypixelAPIPlayer(1)
			t1 := now

			requireNotStored(t, player_uuid, playerdata, t1)
			err := p.StoreStats(ctx, player_uuid, playerdata, t1)
			require.NoError(t, err)
			requireStoredOnce(t, player_uuid, playerdata, t1)

			for i := 1; i < 60; i++ {
				t2 := t1.Add(time.Duration(i) * time.Minute)
				requireNotStored(t, player_uuid, playerdata, t2)
				err = p.StoreStats(ctx, player_uuid, playerdata, t2)
				require.NoError(t, err)
				requireNotStored(t, player_uuid, playerdata, t2)
			}
		})

		t.Run("consecutive duplicate stats are stored if an hour or more apart", func(t *testing.T) {
			t.Parallel()
			player_uuid := newUUID(t)

			playerdata := newHypixelAPIPlayer(1)
			t1 := now

			requireNotStored(t, player_uuid, playerdata, t1)
			err := p.StoreStats(ctx, player_uuid, playerdata, t1)
			require.NoError(t, err)
			requireStoredOnce(t, player_uuid, playerdata, t1)

			// Consecutive duplicate data is more than an hour old -> store this one
			t2 := t1.Add(1 * time.Hour)
			err = p.StoreStats(ctx, player_uuid, playerdata, t2)
			require.NoError(t, err)
			requireStoredOnce(t, player_uuid, playerdata, t2)
		})

		t.Run("non-consecutive duplicate stats are stored", func(t *testing.T) {
			t.Parallel()
			player_uuid := newUUID(t)

			playerdata := newHypixelAPIPlayer(1)
			t1 := now

			requireNotStored(t, player_uuid, playerdata, t1)
			err := p.StoreStats(ctx, player_uuid, playerdata, t1)
			require.NoError(t, err)
			requireStoredOnce(t, player_uuid, playerdata, t1)

			t2 := t1.Add(2 * time.Minute)
			newplayerdata := newHypixelAPIPlayer(1)
			requireNotStored(t, player_uuid, newplayerdata, t2)
			err = p.StoreStats(ctx, player_uuid, newplayerdata, t2)
			require.NoError(t, err)
			requireNotStored(t, player_uuid, newplayerdata, t2)

			// Old duplicate data is not consecutive any more -> store it
			t3 := t2.Add(2 * time.Minute)
			requireNotStored(t, player_uuid, playerdata, t3)
			err = p.StoreStats(ctx, player_uuid, playerdata, t3)
			require.NoError(t, err)
			requireNotStored(t, player_uuid, playerdata, t3)
		})

		t.Run("nothing fails when last stats are an old version", func(t *testing.T) {
			t.Parallel()
			player_uuid := newUUID(t)

			t1 := now
			oldPlayerData := []byte(`{"old_version": {"weird": {"format": 1}}, "xp": "12q3", "1": 1, "all": "lkj"}`)
			normalizedUUID, err := strutils.NormalizeUUID(player_uuid)
			require.NoError(t, err)
			txx, err := db.Beginx()
			require.NoError(t, err)
			defer txx.Rollback()
			_, err = txx.ExecContext(ctx, fmt.Sprintf("SET search_path TO %s", pq.QuoteIdentifier(SCHEMA_NAME)))
			_, err = txx.ExecContext(
				ctx,
				`INSERT INTO stats
		(id, player_uuid, player_data, queried_at, data_format_version)
		VALUES ($1, $2, $3, $4, $5)`,
				newUUID(t),
				normalizedUUID,
				oldPlayerData,
				t1,
				-10,
			)
			require.NoError(t, err)
			err = txx.Commit()
			require.NoError(t, err)

			t2 := t1.Add(2 * time.Minute)
			playerdata := newHypixelAPIPlayer(1)
			err = p.StoreStats(ctx, player_uuid, playerdata, t2)
			require.NoError(t, err)
			requireStoredOnce(t, player_uuid, playerdata, t2)
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

		t.Run("store nil player fails", func(t *testing.T) {
			t.Parallel()
			err := p.StoreStats(ctx, newUUID(t), nil, now)
			require.Error(t, err)
			require.Contains(t, err.Error(), "player is nil")
		})

		t.Run("ensure no db connection leaks", func(t *testing.T) {
			t.Parallel()
			var maxConnections int
			err := db.QueryRowxContext(ctx, "show max_connections").Scan(&maxConnections)
			require.NoError(t, err)
			require.LessOrEqual(t, maxConnections, 1000, "max_connections should be less than 1000 to prevent tests from taking a long time")

			limit := maxConnections + 10

			t.Run("when storing for many different players", func(t *testing.T) {
				t.Parallel()
				for i := 0; i < limit; i++ {
					t1 := now.Add(time.Duration(i) * time.Minute)
					uuid := newUUID(t)
					player := newHypixelAPIPlayer(i)

					err := p.StoreStats(ctx, uuid, player, t1)
					require.NoError(t, err)
					requireStoredOnce(t, uuid, player, t1)
				}
			})
			t.Run("when storing for the same player at the same time", func(t *testing.T) {
				t.Parallel()
				uuid := newUUID(t)
				player := newHypixelAPIPlayer(1)

				for i := 0; i < limit; i++ {
					err := p.StoreStats(ctx, uuid, player, now)
					require.NoError(t, err)
					// Will only ever be stored once since the time is within one minute
					requireStoredOnce(t, uuid, player, now)
				}
			})
		})
	})

	t.Run("GetHistory", func(t *testing.T) {
		t.Parallel()
		type storageInstruction struct {
			uuid      string
			queriedAt time.Time
			player    *processing.HypixelAPIPlayer
		}

		storeStats := func(t *testing.T, p *PostgresStatsPersistor, instructions ...storageInstruction) {
			t.Helper()
			for _, instruction := range instructions {
				err := p.StoreStats(ctx, instruction.uuid, instruction.player, instruction.queriedAt)
				require.NoError(t, err)
			}
		}

		setStoredStats := func(t *testing.T, p *PostgresStatsPersistor, instructions ...storageInstruction) {
			t.Helper()
			txx, err := db.Beginx()
			require.NoError(t, err)
			defer txx.Rollback()

			_, err = txx.ExecContext(ctx, fmt.Sprintf("SET search_path TO %s", pq.QuoteIdentifier(p.schema)))
			require.NoError(t, err)

			_, err = txx.ExecContext(ctx, "DELETE FROM stats")
			require.NoError(t, err)
			err = txx.Commit()

			storeStats(t, p, instructions...)

			var count int
			err = db.QueryRowxContext(ctx, "SELECT COUNT(*) FROM stats").Scan(&count)
			require.NoError(t, err)
			require.Equal(t, len(instructions), count)
		}

		t.Run("evenly spread across a day", func(t *testing.T) {
			p := newPostgresPersistor(t, db, "get_history_evenly_spread_across_a_day")
			janFirst21 := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", 3600*10))

			player_uuid := newUUID(t)

			instructions := []storageInstruction{}
			density := 4
			count := 24 * density
			interval := 24 * time.Hour / time.Duration(count)
			// Evenly distributed stats for 24 hours + 1 extra
			for i := 0; i < count+1; i++ {
				instructions = append(
					instructions,
					storageInstruction{
						uuid:      player_uuid,
						player:    newHypixelAPIPlayer(i),
						queriedAt: janFirst21.Add(time.Duration(i) * interval),
					},
				)
			}

			setStoredStats(t, p, instructions...)

			history, err := p.GetHistory(ctx, player_uuid, janFirst21, janFirst21.Add(24*time.Hour), 25)
			require.NoError(t, err)
			require.Len(t, history, 25)

			for i, playerData := range history {
				offset := i * density
				require.Equal(t, player_uuid, playerData.UUID)
				require.WithinDuration(t, janFirst21.Add(time.Duration(offset)*interval), playerData.QueriedAt, 0)
				// Mock data matches
				require.Equal(t, offset, *playerData.Overall.Kills)
			}
		})

		t.Run("random clusters", func(t *testing.T) {
			p := newPostgresPersistor(t, db, "get_history_random_clusters")
			player_uuid := newUUID(t)
			start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*8))

			instructions := []storageInstruction{
				{player_uuid, start.Add(0 * time.Hour).Add(-1 * time.Minute), newHypixelAPIPlayer(0)},
				{player_uuid, start.Add(0 * time.Hour).Add(7 * time.Minute), newHypixelAPIPlayer(1)},
				{player_uuid, start.Add(0 * time.Hour).Add(17 * time.Minute), newHypixelAPIPlayer(2)},
				{player_uuid, start.Add(0 * time.Hour).Add(37 * time.Minute), newHypixelAPIPlayer(3)},
				{player_uuid, start.Add(2 * time.Hour).Add(40 * time.Minute), newHypixelAPIPlayer(4)},

				{player_uuid, start.Add(2 * time.Hour).Add(45 * time.Minute), newHypixelAPIPlayer(5)},
				{player_uuid, start.Add(2 * time.Hour).Add(50 * time.Minute), newHypixelAPIPlayer(6)},
				{player_uuid, start.Add(2 * time.Hour).Add(55 * time.Minute), newHypixelAPIPlayer(7)},

				{player_uuid, start.Add(3 * time.Hour).Add(1 * time.Minute), newHypixelAPIPlayer(8)},
				{player_uuid, start.Add(3 * time.Hour).Add(47 * time.Minute), newHypixelAPIPlayer(9)},
				{player_uuid, start.Add(3 * time.Hour).Add(59 * time.Minute), newHypixelAPIPlayer(10)},
				{player_uuid, start.Add(4 * time.Hour).Add(1 * time.Minute), newHypixelAPIPlayer(11)},
			}

			setStoredStats(t, p, instructions...)

			history, err := p.GetHistory(ctx, player_uuid, start, start.Add(4*time.Hour), 16+1)
			require.NoError(t, err)

			expectedHistory := []storageInstruction{
				instructions[1],
				instructions[2],
				instructions[3],
				instructions[4],
				instructions[5],
				instructions[8],
				instructions[9],
				instructions[10],
			}

			require.Len(t, history, len(expectedHistory))

			for i, expectedPIT := range expectedHistory {
				playerPIT := history[i]

				require.Equal(t, player_uuid, expectedPIT.uuid)
				require.Equal(t, player_uuid, playerPIT.UUID)

				// Mock data matches
				require.Equal(t, *expectedPIT.player.Stats.Bedwars.Kills, *playerPIT.Overall.Kills)

				require.WithinDuration(t, expectedPIT.queriedAt, playerPIT.QueriedAt, 0)
			}
		})
	})
}
