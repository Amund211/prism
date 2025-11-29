package playerrepository

import (
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jmoiron/sqlx"
	"github.com/lib/pq"
	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/adapters/database"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/domaintest"
	"github.com/Amund211/flashlight/internal/strutils"
)

func newPostgresPlayerRepository(t *testing.T, db *sqlx.DB, schema string) *PostgresPlayerRepository {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))

	db.MustExec(fmt.Sprintf("DROP SCHEMA IF EXISTS %s CASCADE", pq.QuoteIdentifier(schema)))

	migrator := database.NewDatabaseMigrator(db, logger)

	err := migrator.Migrate(t.Context(), schema)
	require.NoError(t, err)

	return NewPostgresPlayerRepository(db, schema)
}

func TestPostgresPlayerRepository(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping db tests in short mode.")
	}
	t.Parallel()

	requireValidDBID := func(t *testing.T, id *string) {
		t.Helper()
		require.NotNil(t, id)
		parsed, err := uuid.Parse(*id)
		require.NoError(t, err)

		require.Equal(t, uuid.Version(7), parsed.Version())
	}

	ctx := t.Context()
	db, err := database.NewPostgresDatabase(database.LOCAL_CONNECTION_STRING)
	require.NoError(t, err)

	now := time.Now()

	t.Run("StorePlayer", func(t *testing.T) {
		t.Parallel()

		SCHEMA_NAME := "store_stats"
		p := newPostgresPlayerRepository(t, db, SCHEMA_NAME)

		requireStored := func(t *testing.T, player *domain.PlayerPIT, targetCount int) {
			t.Helper()

			normalizedUUID, err := strutils.NormalizeUUID(player.UUID)
			require.NoError(t, err)

			playerData, err := playerToDataStorage(player)
			require.NoError(t, err)

			txx, err := db.Beginx()
			require.NoError(t, err)
			defer txx.Rollback()

			_, err = txx.ExecContext(ctx, fmt.Sprintf("SET search_path TO %s", pq.QuoteIdentifier(SCHEMA_NAME)))
			require.NoError(t, err)

			row := txx.QueryRowx("SELECT COUNT(*) FROM stats WHERE player_uuid = $1 AND player_data = $2 AND queried_at = $3", normalizedUUID, playerData, player.QueriedAt)
			require.NoError(t, row.Err())

			var count int
			require.NoError(t, row.Scan(&count))
			require.Equal(t, targetCount, count)

			if normalizedUUID != player.UUID {
				row := txx.QueryRowx("SELECT COUNT(*) FROM stats WHERE player_uuid = $1 AND player_data = $2 AND queried_at = $3", player.UUID, playerData, player.QueriedAt)
				require.NoError(t, row.Err())

				var count int
				require.NoError(t, row.Scan(&count))
				require.Equal(t, 0, count, "un-normalized UUID should not be stored")
			}

			err = txx.Commit()
			require.NoError(t, err)
		}

		requireNotStored := func(t *testing.T, player *domain.PlayerPIT) {
			t.Helper()
			requireStored(t, player, 0)
		}

		requireStoredOnce := func(t *testing.T, player *domain.PlayerPIT) {
			t.Helper()
			requireStored(t, player, 1)
		}

		t.Run("store empty object", func(t *testing.T) {
			t.Parallel()

			playerUUID := domaintest.NewUUID(t)
			player := domaintest.NewPlayerBuilder(playerUUID, now).WithGamesPlayed(0).BuildPtr()

			requireNotStored(t, player)
			err := p.StorePlayer(ctx, player)
			require.NoError(t, err)
			requireStoredOnce(t, player)
		})

		t.Run("store multiple for same user", func(t *testing.T) {
			t.Parallel()
			playerUUID := domaintest.NewUUID(t)
			t1 := now
			t2 := t1.Add(3 * time.Minute)

			player1 := domaintest.NewPlayerBuilder(playerUUID, t1).WithGamesPlayed(1).BuildPtr()
			player2 := domaintest.NewPlayerBuilder(playerUUID, t2).WithGamesPlayed(2).BuildPtr()

			requireNotStored(t, player1)
			err := p.StorePlayer(ctx, player1)
			require.NoError(t, err)
			requireStoredOnce(t, player1)

			requireNotStored(t, player2)
			err = p.StorePlayer(ctx, player2)
			require.NoError(t, err)
			requireStoredOnce(t, player2)

			// We never stored these combinations
			player1t2 := domaintest.NewPlayerBuilder(playerUUID, t2).WithGamesPlayed(1).BuildPtr()
			requireNotStored(t, player1t2)
			player2t1 := domaintest.NewPlayerBuilder(playerUUID, t1).WithGamesPlayed(2).BuildPtr()
			requireNotStored(t, player2t1)
		})

		t.Run("stats are stored within a short time span if they are different", func(t *testing.T) {
			t.Parallel()
			playerUUID := domaintest.NewUUID(t)
			t1 := now

			player1 := domaintest.NewPlayerBuilder(playerUUID, t1).WithGamesPlayed(1).BuildPtr()

			requireNotStored(t, player1)
			err := p.StorePlayer(ctx, player1)
			require.NoError(t, err)
			requireStoredOnce(t, player1)

			t2 := t1.Add(time.Millisecond)
			player2 := domaintest.NewPlayerBuilder(playerUUID, t2).WithGamesPlayed(2).BuildPtr()

			requireNotStored(t, player2)
			err = p.StorePlayer(ctx, player2)
			require.NoError(t, err)
			requireStoredOnce(t, player2)
		})

		t.Run("consecutive duplicate stats are not stored", func(t *testing.T) {
			t.Parallel()
			playerUUID := domaintest.NewUUID(t)

			t1 := now
			player1 := domaintest.NewPlayerBuilder(playerUUID, t1).WithGamesPlayed(1).BuildPtr()

			requireNotStored(t, player1)
			err := p.StorePlayer(ctx, player1)
			require.NoError(t, err)
			requireStoredOnce(t, player1)

			for i := 1; i < 60; i++ {
				t2 := t1.Add(time.Duration(i) * time.Minute)
				player2 := domaintest.NewPlayerBuilder(playerUUID, t2).WithGamesPlayed(1).BuildPtr()
				requireNotStored(t, player2)
				err = p.StorePlayer(ctx, player2)
				require.NoError(t, err)
				requireNotStored(t, player2)
			}
		})

		t.Run("consecutive duplicate stats are stored if an hour or more apart", func(t *testing.T) {
			t.Parallel()
			playerUUID := domaintest.NewUUID(t)

			t1 := now
			player1 := domaintest.NewPlayerBuilder(playerUUID, t1).WithGamesPlayed(1).BuildPtr()

			requireNotStored(t, player1)
			err := p.StorePlayer(ctx, player1)
			require.NoError(t, err)
			requireStoredOnce(t, player1)

			// Consecutive duplicate data is more than an hour old -> store this one
			t2 := t1.Add(1 * time.Hour)
			player2 := domaintest.NewPlayerBuilder(playerUUID, t2).WithGamesPlayed(1).BuildPtr()

			err = p.StorePlayer(ctx, player2)
			require.NoError(t, err)
			requireStoredOnce(t, player2)
		})

		t.Run("non-consecutive duplicate stats are stored", func(t *testing.T) {
			t.Parallel()
			playerUUID := domaintest.NewUUID(t)

			t1 := now
			player1 := domaintest.NewPlayerBuilder(playerUUID, t1).WithGamesPlayed(1).BuildPtr()

			requireNotStored(t, player1)
			err := p.StorePlayer(ctx, player1)
			require.NoError(t, err)
			requireStoredOnce(t, player1)

			t2 := t1.Add(2 * time.Minute)
			player2 := domaintest.NewPlayerBuilder(playerUUID, t2).WithGamesPlayed(2).BuildPtr()

			requireNotStored(t, player2)
			err = p.StorePlayer(ctx, player2)
			require.NoError(t, err)
			requireStoredOnce(t, player2)

			// Old duplicate data is not consecutive any more -> store it
			t3 := t2.Add(2 * time.Minute)
			player3 := domaintest.NewPlayerBuilder(playerUUID, t3).WithGamesPlayed(1).BuildPtr()
			requireNotStored(t, player3)
			err = p.StorePlayer(ctx, player3)
			require.NoError(t, err)
			requireStoredOnce(t, player3)
		})

		t.Run("nothing fails when last stats are an old version", func(t *testing.T) {
			t.Parallel()
			playerUUID := domaintest.NewUUID(t)

			t1 := now
			oldPlayerData := []byte(`{"old_version": {"weird": {"format": 1}}, "xp": "12q3", "1": 1, "all": "lkj"}`)
			normalizedUUID, err := strutils.NormalizeUUID(playerUUID)
			require.NoError(t, err)
			txx, err := db.Beginx()
			require.NoError(t, err)
			defer txx.Rollback()

			_, err = txx.ExecContext(ctx, fmt.Sprintf("SET search_path TO %s", pq.QuoteIdentifier(SCHEMA_NAME)))
			require.NoError(t, err)

			_, err = txx.ExecContext(
				ctx,
				`INSERT INTO stats
		(id, player_uuid, player_data, queried_at, data_format_version)
		VALUES ($1, $2, $3, $4, $5)`,
				domaintest.NewUUID(t),
				normalizedUUID,
				oldPlayerData,
				t1,
				-10,
			)
			require.NoError(t, err)
			err = txx.Commit()
			require.NoError(t, err)

			t2 := t1.Add(2 * time.Minute)
			player2 := domaintest.NewPlayerBuilder(playerUUID, t2).WithGamesPlayed(1).BuildPtr()
			err = p.StorePlayer(ctx, player2)
			require.NoError(t, err)
			requireStoredOnce(t, player2)
		})

		t.Run("same data for multiple users", func(t *testing.T) {
			t.Parallel()
			t1 := now
			uuid1 := domaintest.NewUUID(t)
			uuid2 := domaintest.NewUUID(t)
			player1 := domaintest.NewPlayerBuilder(uuid1, t1).WithGamesPlayed(3).BuildPtr()
			player2 := domaintest.NewPlayerBuilder(uuid2, t1).WithGamesPlayed(3).BuildPtr()

			requireNotStored(t, player1)
			err := p.StorePlayer(ctx, player1)
			require.NoError(t, err)
			requireStoredOnce(t, player1)

			requireNotStored(t, player2)
			err = p.StorePlayer(ctx, player2)
			require.NoError(t, err)
			requireStoredOnce(t, player2)

			requireStoredOnce(t, player1)
		})

		t.Run("store nil player fails", func(t *testing.T) {
			t.Parallel()
			err := p.StorePlayer(ctx, nil)
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
				for i := range limit {
					t1 := now.Add(time.Duration(i) * time.Minute)
					playerUUID := domaintest.NewUUID(t)
					player := domaintest.NewPlayerBuilder(playerUUID, t1).WithGamesPlayed(i).BuildPtr()

					err := p.StorePlayer(ctx, player)
					require.NoError(t, err)
					requireStoredOnce(t, player)
				}
			})
			t.Run("when storing for the same player at the same time", func(t *testing.T) {
				t.Parallel()
				playerUUID := domaintest.NewUUID(t)
				t1 := now
				player := domaintest.NewPlayerBuilder(playerUUID, t1).WithGamesPlayed(1).BuildPtr()

				for range limit {
					err := p.StorePlayer(ctx, player)
					require.NoError(t, err)
					// Will only ever be stored once since the time is within one minute
					requireStoredOnce(t, player)
				}
			})
		})

		t.Run("store creates uuidv7 as db id", func(t *testing.T) {
			t.Parallel()

			playerUUID := domaintest.NewUUID(t)
			player := domaintest.NewPlayerBuilder(playerUUID, now).WithGamesPlayed(11).BuildPtr()

			requireNotStored(t, player)
			err := p.StorePlayer(ctx, player)
			require.NoError(t, err)
			requireStoredOnce(t, player)

			txx, err := db.Beginx()
			require.NoError(t, err)
			defer txx.Rollback()

			_, err = txx.ExecContext(ctx, fmt.Sprintf("SET search_path TO %s", pq.QuoteIdentifier(SCHEMA_NAME)))
			require.NoError(t, err)

			// Only one row for this player should exist
			var dbID string
			row := txx.GetContext(ctx, &dbID, "SELECT id FROM stats WHERE player_uuid = $1", playerUUID)
			require.NoError(t, row)

			err = txx.Commit()
			require.NoError(t, err)

			requireValidDBID(t, &dbID)
		})

		t.Run("cannot store player with existing DBID", func(t *testing.T) {
			t.Parallel()

			uuidv7, err := uuid.NewV7()
			require.NoError(t, err)

			dbID := uuidv7.String()
			playerUUID := domaintest.NewUUID(t)
			player := domaintest.NewPlayerBuilder(playerUUID, now).WithDBID(&dbID).BuildPtr()

			err = p.StorePlayer(ctx, player)
			require.Error(t, err)
			require.Contains(t, err.Error(), "already has a DBID")
		})
	})

	t.Run("GetHistory", func(t *testing.T) {
		t.Parallel()

		storePlayer := func(t *testing.T, p PlayerRepository, players ...*domain.PlayerPIT) {
			t.Helper()
			for _, player := range players {
				err := p.StorePlayer(ctx, player)
				require.NoError(t, err)
			}
		}

		setStoredStats := func(t *testing.T, p *PostgresPlayerRepository, players ...*domain.PlayerPIT) {
			t.Helper()
			txx, err := db.Beginx()
			require.NoError(t, err)
			defer txx.Rollback()

			_, err = txx.ExecContext(ctx, fmt.Sprintf("SET search_path TO %s", pq.QuoteIdentifier(p.schema)))
			require.NoError(t, err)

			_, err = txx.ExecContext(ctx, "DELETE FROM stats")
			require.NoError(t, err)
			err = txx.Commit()
			require.NoError(t, err)

			storePlayer(t, p, players...)

			txx, err = db.Beginx()
			require.NoError(t, err)
			defer txx.Rollback()

			_, err = txx.ExecContext(ctx, fmt.Sprintf("SET search_path TO %s", pq.QuoteIdentifier(p.schema)))
			require.NoError(t, err)

			var count int
			err = txx.QueryRowxContext(ctx, "SELECT COUNT(*) FROM stats").Scan(&count)
			require.NoError(t, err)
			require.Equal(t, len(players), count)

			err = txx.Commit()
			require.NoError(t, err)
		}

		requireDistribution := func(t *testing.T, history []domain.PlayerPIT, expectedDistribution []time.Time) {
			t.Helper()
			require.Len(t, history, len(expectedDistribution))

			for i, expectedTime := range expectedDistribution {
				require.WithinDuration(t, expectedTime, history[i].QueriedAt, 0, fmt.Sprintf("index %d", i))
			}
		}

		t.Run("evenly spread across a day", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPlayerRepository(t, db, "get_history_evenly_spread_across_a_day")
			janFirst21 := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", 3600*10))

			playerUUID := domaintest.NewUUID(t)

			players := []*domain.PlayerPIT{}
			density := 4
			count := 24 * density
			interval := 24 * time.Hour / time.Duration(count)
			// Evenly distributed stats for 24 hours + 1 extra
			for i := range count + 1 {
				players = append(
					players,
					domaintest.NewPlayerBuilder(playerUUID, janFirst21.Add(time.Duration(i)*interval)).WithGamesPlayed(i).BuildPtr(),
				)
			}

			require.Len(t, players, 24*4+1)

			setStoredStats(t, p, players...)

			history, err := p.GetHistory(ctx, playerUUID, janFirst21, janFirst21.Add(24*time.Hour), 48)
			require.NoError(t, err)
			expectedDistribution := []time.Time{}
			for i := range 24 {
				startOfHour := janFirst21.Add(time.Duration(i) * time.Hour)
				expectedDistribution = append(expectedDistribution, startOfHour)
				if i != 23 {
					expectedDistribution = append(expectedDistribution, startOfHour.Add(45*time.Minute))
				} else {
					expectedDistribution = append(expectedDistribution, startOfHour.Add(time.Hour))
				}

			}
			requireDistribution(t, history, expectedDistribution)
		})

		t.Run("random clusters", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPlayerRepository(t, db, "get_history_random_clusters")
			playerUUID := domaintest.NewUUID(t)
			start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*8))

			players := make([]*domain.PlayerPIT, 13)
			// Before start
			players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(0*time.Hour).Add(-1*time.Minute)).WithGamesPlayed(0).BuildPtr()

			// First 30 min interval
			players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(0*time.Hour).Add(7*time.Minute)).WithGamesPlayed(1).BuildPtr()
			players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(0*time.Hour).Add(17*time.Minute)).WithGamesPlayed(2).BuildPtr()

			// Second 30 min interval
			players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(0*time.Hour).Add(37*time.Minute)).WithGamesPlayed(3).BuildPtr()

			// Sixth 30 min interval
			players[4] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(40*time.Minute)).WithGamesPlayed(4).BuildPtr()
			players[5] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(45*time.Minute)).WithGamesPlayed(5).BuildPtr()
			players[6] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(50*time.Minute)).WithGamesPlayed(6).BuildPtr()
			players[7] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(55*time.Minute)).WithGamesPlayed(7).BuildPtr()

			// Seventh 30 min interval
			players[8] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(1*time.Minute)).WithGamesPlayed(8).BuildPtr()

			// Eighth 30 min interval
			players[9] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(47*time.Minute)).WithGamesPlayed(9).BuildPtr()
			players[10] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(59*time.Minute)).WithGamesPlayed(0).BuildPtr()

			// After end
			players[11] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour).Add(1*time.Minute)).WithGamesPlayed(1).BuildPtr()
			players[12] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4000*time.Hour).Add(1*time.Minute)).WithGamesPlayed(2).BuildPtr()

			setStoredStats(t, p, players...)

			// Get entries at the start and end of each 30 min interval (8 in total)
			history, err := p.GetHistory(ctx, playerUUID, start, start.Add(4*time.Hour), 16)
			require.NoError(t, err)

			expectedHistory := []*domain.PlayerPIT{
				players[1],
				players[2],

				players[3],

				players[4],
				players[7],

				players[8],

				players[9],
				players[10],
			}

			require.Len(t, history, len(expectedHistory))

			for i, expectedPIT := range expectedHistory {
				playerPIT := history[i]

				require.Equal(t, playerUUID, expectedPIT.UUID)
				require.Equal(t, playerUUID, playerPIT.UUID)

				// Mock data matches
				require.Equal(t, expectedPIT.Overall.Kills, playerPIT.Overall.Kills)

				require.WithinDuration(t, expectedPIT.QueriedAt, playerPIT.QueriedAt, 0)
			}
		})

		t.Run("no duplicates returned", func(t *testing.T) {
			// The current implementation gets both the first and last stats in each interval
			// Make sure these are not the same instance.

			t.Parallel()
			p := newPostgresPlayerRepository(t, db, "no_duplicates_returned")

			t.Run("single stat stored", func(t *testing.T) {
				t.Parallel()

				start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*8))
				end := start.Add(24 * time.Hour)
				for _, queriedAt := range []time.Time{
					start,
					start.Add(1 * time.Microsecond),
					start.Add(1 * time.Second),
					start.Add(1 * time.Hour),
					start.Add(3 * time.Hour).Add(15 * time.Minute),
					start.Add(14 * time.Hour).Add(1 * time.Minute),
					end,
				} {
					for limit := 2; limit < 10; limit++ {
						t.Run(fmt.Sprintf("limit %d, queriedAt %s", limit, queriedAt), func(t *testing.T) {
							t.Parallel()
							playerUUID := domaintest.NewUUID(t)
							players := []*domain.PlayerPIT{
								domaintest.NewPlayerBuilder(playerUUID, queriedAt).WithGamesPlayed(1).BuildPtr(),
							}

							storePlayer(t, p, players...)

							history, err := p.GetHistory(ctx, playerUUID, start, end, limit)
							require.NoError(t, err)

							require.Len(t, history, 1)

							expectedPIT := players[0]
							playerPIT := history[0]

							require.Equal(t, playerUUID, expectedPIT.UUID)
							require.Equal(t, playerUUID, playerPIT.UUID)

							// Mock data matches
							require.Equal(t, expectedPIT.Overall.Kills, playerPIT.Overall.Kills)

							require.WithinDuration(t, expectedPIT.QueriedAt, playerPIT.QueriedAt, 0)
						})
					}
				}
			})

			t.Run("multiple stats stored", func(t *testing.T) {
				t.Parallel()
				start := time.Date(2021, time.March, 24, 15, 59, 31, 987_000_000, time.FixedZone("UTC", -3600*3))
				end := start.Add(24 * time.Hour)

				for limit := 2; limit < 10; limit++ {
					t.Run(fmt.Sprintf("limit %d", limit), func(t *testing.T) {
						t.Parallel()

						playerUUID := domaintest.NewUUID(t)
						players := []*domain.PlayerPIT{
							domaintest.NewPlayerBuilder(playerUUID, start.Add(time.Minute)).WithGamesPlayed(1).BuildPtr(),
							domaintest.NewPlayerBuilder(playerUUID, end.Add(-1*time.Minute)).WithGamesPlayed(0).BuildPtr(),
						}

						storePlayer(t, p, players...)

						history, err := p.GetHistory(ctx, playerUUID, start, end, limit)
						require.NoError(t, err)

						require.Len(t, history, 2)

						for i, expectedPIT := range players {
							playerPIT := history[i]

							require.Equal(t, playerUUID, expectedPIT.UUID)
							require.Equal(t, playerUUID, playerPIT.UUID)

							// Mock data matches
							require.Equal(t, expectedPIT.Overall.Kills, playerPIT.Overall.Kills)

							require.WithinDuration(t, expectedPIT.QueriedAt, playerPIT.QueriedAt, 0)
						}
					})
				}
			})

			t.Run("db ids returned", func(t *testing.T) {
				t.Parallel()
				start := time.Date(2023, time.September, 16, 15, 41, 31, 987_000_000, time.FixedZone("UTC", 3600*7))
				end := start.Add(24 * time.Hour)

				playerUUID := domaintest.NewUUID(t)
				players := []*domain.PlayerPIT{
					domaintest.NewPlayerBuilder(playerUUID, start.Add(time.Minute)).WithGamesPlayed(1).BuildPtr(),
					domaintest.NewPlayerBuilder(playerUUID, end.Add(-1*time.Minute)).WithGamesPlayed(0).BuildPtr(),
				}

				storePlayer(t, p, players...)

				history, err := p.GetHistory(ctx, playerUUID, start, end, 50)
				require.NoError(t, err)

				require.Len(t, history, 2)

				firstDBID := history[0].DBID
				requireValidDBID(t, firstDBID)
				secondDBID := history[1].DBID
				requireValidDBID(t, secondDBID)

				// DB ids should be stable
				history, err = p.GetHistory(ctx, playerUUID, start, end, 50)
				require.NoError(t, err)
				require.Len(t, history, 2)

				require.Equal(t, *firstDBID, *history[0].DBID)
				require.Equal(t, *secondDBID, *history[1].DBID)
			})
		})
	})

	t.Run("GetSessions", func(t *testing.T) {
		t.Parallel()
		storePlayer := func(t *testing.T, p PlayerRepository, players ...*domain.PlayerPIT) []*domain.PlayerPIT {
			t.Helper()
			playerData := make([]*domain.PlayerPIT, len(players))
			for i, player := range players {
				// Add a random number to prevent de-duplication of the stored stats
				player.Solo.Winstreak = &i
				err := p.StorePlayer(ctx, player)
				require.NoError(t, err)

				history, err := p.GetHistory(ctx, player.UUID, player.QueriedAt, player.QueriedAt.Add(1*time.Microsecond), 2)
				require.NoError(t, err)
				require.Len(t, history, 1)
				playerData[i] = &history[0]
			}
			return playerData
		}

		requireEqualSessions := func(t *testing.T, expected, actual []domain.Session) {
			t.Helper()

			type normalizedPlayerPIT struct {
				queriedAtISO  string
				uuid          string
				experience    int64
				gamesPlayed   int
				soloWinstreak int
			}

			type normalizedSession struct {
				start       normalizedPlayerPIT
				end         normalizedPlayerPIT
				consecutive bool
			}

			normalizePlayerData := func(player *domain.PlayerPIT) normalizedPlayerPIT {
				soloWinstreak := -1
				if player.Solo.Winstreak != nil {
					soloWinstreak = *player.Solo.Winstreak
				}
				return normalizedPlayerPIT{
					queriedAtISO:  player.QueriedAt.Format(time.RFC3339),
					uuid:          player.UUID,
					experience:    player.Experience,
					gamesPlayed:   player.Overall.GamesPlayed,
					soloWinstreak: soloWinstreak,
				}

			}

			normalizeSessions := func(sessions []domain.Session) []normalizedSession {
				normalized := make([]normalizedSession, len(sessions))
				for i, session := range sessions {
					normalized[i] = normalizedSession{
						start:       normalizePlayerData(&session.Start),
						end:         normalizePlayerData(&session.End),
						consecutive: session.Consecutive,
					}
				}
				return normalized
			}

			require.Equal(t, normalizeSessions(expected), normalizeSessions(actual))
		}

		t.Run("random clusters", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPlayerRepository(t, db, "get_sessions_random_clusters")
			playerUUID := domaintest.NewUUID(t)
			start := time.Date(2022, time.February, 14, 0, 0, 0, 0, time.FixedZone("UTC", 3600*1))

			players := make([]*domain.PlayerPIT, 26)
			// Ended session befor the start
			players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(-8*time.Hour).Add(-1*time.Minute)).WithGamesPlayed(10).WithExperience(1_000).BuildPtr()
			players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(-8*time.Hour).Add(7*time.Minute)).WithGamesPlayed(11).WithExperience(1_300).BuildPtr()
			players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(-8*time.Hour).Add(17*time.Minute)).WithGamesPlayed(12).WithExperience(1_600).BuildPtr()

			// Session starting just before the start
			// Some inactivity at the start of the session
			players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(0*time.Hour).Add(-37*time.Minute)).WithGamesPlayed(12).WithExperience(1_600).BuildPtr()
			players[4] = domaintest.NewPlayerBuilder(playerUUID, start.Add(0*time.Hour).Add(-27*time.Minute)).WithGamesPlayed(12).WithExperience(1_600).BuildPtr()
			players[5] = domaintest.NewPlayerBuilder(playerUUID, start.Add(0*time.Hour).Add(-17*time.Minute)).WithGamesPlayed(12).WithExperience(1_600).BuildPtr()
			players[6] = domaintest.NewPlayerBuilder(playerUUID, start.Add(0*time.Hour).Add(-12*time.Minute)).WithGamesPlayed(13).WithExperience(1_900).BuildPtr()
			players[7] = domaintest.NewPlayerBuilder(playerUUID, start.Add(0*time.Hour).Add(2*time.Minute)).WithGamesPlayed(14).WithExperience(2_200).BuildPtr()
			// One hour space between entries
			players[8] = domaintest.NewPlayerBuilder(playerUUID, start.Add(0*time.Hour).Add(38*time.Minute)).WithGamesPlayed(15).WithExperience(7_200).BuildPtr()
			players[9] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(38*time.Minute)).WithGamesPlayed(16).WithExperience(7_900).BuildPtr()
			// One hour space between stat change, with some inactivity events in between
			players[10] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(45*time.Minute)).WithGamesPlayed(17).WithExperience(8_900).BuildPtr()
			players[11] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(55*time.Minute)).WithGamesPlayed(17).WithExperience(8_900).BuildPtr()
			players[12] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(5*time.Minute)).WithGamesPlayed(17).WithExperience(8_900).BuildPtr()
			players[13] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(15*time.Minute)).WithGamesPlayed(17).WithExperience(8_900).BuildPtr()
			players[14] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(25*time.Minute)).WithGamesPlayed(17).WithExperience(8_900).BuildPtr()
			players[15] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(35*time.Minute)).WithGamesPlayed(17).WithExperience(8_900).BuildPtr()
			players[16] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(45*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).BuildPtr()
			// Some inactivity at the end
			players[17] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(55*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).BuildPtr()
			players[18] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(5*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).BuildPtr()
			players[19] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(15*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).BuildPtr()
			players[20] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(25*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).BuildPtr()
			players[21] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(35*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).BuildPtr()
			players[22] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(45*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).BuildPtr()
			players[23] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(55*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).BuildPtr()

			// New activity 71 minutues after the last entry -> new session
			players[24] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(56*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).BuildPtr()
			players[25] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour).Add(16*time.Minute)).WithGamesPlayed(19).WithExperience(10_800).BuildPtr()

			playerData := storePlayer(t, p, players...)

			sessions, err := p.GetSessions(ctx, playerUUID, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []domain.Session{
				{
					Start:       *playerData[5],
					End:         *playerData[16],
					Consecutive: true,
				},
				{
					Start:       *playerData[24],
					End:         *playerData[25],
					Consecutive: true,
				},
			}
			requireEqualSessions(t, expectedSessions, sessions)
		})

		t.Run("Single stat", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPlayerRepository(t, db, "get_sessions_single")
			playerUUID := domaintest.NewUUID(t)
			start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*8))

			players := make([]*domain.PlayerPIT, 1)
			players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(6*time.Hour).Add(7*time.Minute)).WithGamesPlayed(11).WithExperience(1_300).BuildPtr()

			_ = storePlayer(t, p, players...)

			sessions, err := p.GetSessions(ctx, playerUUID, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			require.Len(t, sessions, 0)
		})

		t.Run("Single stat at the start", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPlayerRepository(t, db, "get_sessions_single_at_start")
			playerUUID := domaintest.NewUUID(t)
			start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*8))

			players := make([]*domain.PlayerPIT, 3)
			players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(6*time.Hour).Add(7*time.Minute)).WithGamesPlayed(9).WithExperience(1_000).BuildPtr()

			players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(8*time.Hour).Add(-1*time.Minute)).WithGamesPlayed(10).WithExperience(1_100).BuildPtr()
			players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(8*time.Hour).Add(7*time.Minute)).WithGamesPlayed(11).WithExperience(1_300).BuildPtr()

			playerData := storePlayer(t, p, players...)

			sessions, err := p.GetSessions(ctx, playerUUID, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []domain.Session{
				{
					Start:       *playerData[1],
					End:         *playerData[2],
					Consecutive: true,
				},
			}
			requireEqualSessions(t, expectedSessions, sessions)
		})

		t.Run("Single stat at the end", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPlayerRepository(t, db, "get_sessions_single_at_end")
			playerUUID := domaintest.NewUUID(t)
			start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*8))

			players := make([]*domain.PlayerPIT, 3)
			players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(6*time.Hour).Add(-1*time.Minute)).WithGamesPlayed(10).WithExperience(1_000).BuildPtr()
			players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(6*time.Hour).Add(7*time.Minute)).WithGamesPlayed(11).WithExperience(1_300).BuildPtr()

			players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(8*time.Hour).Add(7*time.Minute)).WithGamesPlayed(12).WithExperience(1_600).BuildPtr()

			playerData := storePlayer(t, p, players...)

			sessions, err := p.GetSessions(ctx, playerUUID, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []domain.Session{
				{
					Start:       *playerData[0],
					End:         *playerData[1],
					Consecutive: true,
				},
			}
			requireEqualSessions(t, expectedSessions, sessions)
		})

		t.Run("Single stat at start and end", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPlayerRepository(t, db, "get_sessions_single_at_start_and_end")
			playerUUID := domaintest.NewUUID(t)
			start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*2))

			players := make([]*domain.PlayerPIT, 4)
			players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(5*time.Hour).Add(7*time.Minute)).WithGamesPlayed(9).WithExperience(1_000).BuildPtr()

			players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(8*time.Hour).Add(-1*time.Minute)).WithGamesPlayed(10).WithExperience(1_000).BuildPtr()
			players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(8*time.Hour).Add(7*time.Minute)).WithGamesPlayed(11).WithExperience(1_300).BuildPtr()

			players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(10*time.Hour).Add(7*time.Minute)).WithGamesPlayed(12).WithExperience(1_600).BuildPtr()

			playerData := storePlayer(t, p, players...)

			sessions, err := p.GetSessions(ctx, playerUUID, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []domain.Session{
				{
					Start:       *playerData[1],
					End:         *playerData[2],
					Consecutive: true,
				},
			}
			requireEqualSessions(t, expectedSessions, sessions)
		})

		t.Run("No stats", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPlayerRepository(t, db, "get_sessions_no_stats")
			playerUUID := domaintest.NewUUID(t)
			start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*10))

			players := make([]*domain.PlayerPIT, 0)

			_ = storePlayer(t, p, players...)

			sessions, err := p.GetSessions(ctx, playerUUID, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			require.Len(t, sessions, 0)
		})

		t.Run("inactivity between sessions", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPlayerRepository(t, db, "get_sessions_inactivity_between_sessions")
			playerUUID := domaintest.NewUUID(t)
			start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*2))

			players := make([]*domain.PlayerPIT, 13)
			players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(30*time.Minute)).WithGamesPlayed(16).WithExperience(9_200).BuildPtr()
			players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(35*time.Minute)).WithGamesPlayed(16).WithExperience(9_200).BuildPtr()
			players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(45*time.Minute)).WithGamesPlayed(17).WithExperience(9_400).BuildPtr()
			players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(55*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).BuildPtr()
			players[4] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(5*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).BuildPtr()
			players[5] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(15*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).BuildPtr()
			players[6] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(25*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).BuildPtr()
			players[7] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(35*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).BuildPtr()
			players[8] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(45*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).BuildPtr()
			players[9] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(55*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).BuildPtr()
			players[10] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(56*time.Minute)).WithGamesPlayed(18).WithExperience(9_500).BuildPtr()
			players[11] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour).Add(16*time.Minute)).WithGamesPlayed(19).WithExperience(10_800).BuildPtr()
			players[12] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour).Add(20*time.Minute)).WithGamesPlayed(19).WithExperience(10_800).BuildPtr()

			playerData := storePlayer(t, p, players...)

			sessions, err := p.GetSessions(ctx, playerUUID, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []domain.Session{
				{
					Start:       *playerData[1],
					End:         *playerData[3],
					Consecutive: true,
				},
				{
					Start:       *playerData[10],
					End:         *playerData[11],
					Consecutive: true,
				},
			}
			requireEqualSessions(t, expectedSessions, sessions)
		})

		t.Run("1 hr inactivity between sessions", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPlayerRepository(t, db, "get_sessions_1_hr_inactivity_between_sessions")
			playerUUID := domaintest.NewUUID(t)
			start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*2))

			players := make([]*domain.PlayerPIT, 4)
			// Session 1
			players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(5*time.Minute)).WithGamesPlayed(16).WithExperience(9_200).BuildPtr()
			players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(30*time.Minute)).WithGamesPlayed(17).WithExperience(9_400).BuildPtr()
			// Session 2
			players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(45*time.Minute)).WithGamesPlayed(17).WithExperience(9_400).BuildPtr()
			players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(31*time.Minute)).WithGamesPlayed(18).WithExperience(10_800).BuildPtr()

			playerData := storePlayer(t, p, players...)

			sessions, err := p.GetSessions(ctx, playerUUID, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []domain.Session{
				{
					Start:       *playerData[0],
					End:         *playerData[1],
					Consecutive: true,
				},
				{
					Start:       *playerData[2],
					End:         *playerData[3],
					Consecutive: true,
				},
			}
			requireEqualSessions(t, expectedSessions, sessions)
		})

		t.Run("sessions before and after", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPlayerRepository(t, db, "get_sessions_before_and_after")
			playerUUID := domaintest.NewUUID(t)
			start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*2))

			players := make([]*domain.PlayerPIT, 8)
			players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(-25*time.Hour).Add(5*time.Minute)).WithGamesPlayed(16).WithExperience(9_200).BuildPtr()
			players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(-25*time.Hour).Add(30*time.Minute)).WithGamesPlayed(17).WithExperience(9_400).BuildPtr()

			players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(-16*time.Hour).Add(5*time.Minute)).WithGamesPlayed(17).WithExperience(9_400).BuildPtr()
			players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(-16*time.Hour).Add(30*time.Minute)).WithGamesPlayed(18).WithExperience(9_900).BuildPtr()

			players[4] = domaintest.NewPlayerBuilder(playerUUID, start.Add(25*time.Hour).Add(5*time.Minute)).WithGamesPlayed(18).WithExperience(9_900).BuildPtr()
			players[5] = domaintest.NewPlayerBuilder(playerUUID, start.Add(25*time.Hour).Add(30*time.Minute)).WithGamesPlayed(19).WithExperience(10_900).BuildPtr()

			players[6] = domaintest.NewPlayerBuilder(playerUUID, start.Add(45*time.Hour).Add(5*time.Minute)).WithGamesPlayed(19).WithExperience(10_900).BuildPtr()
			players[7] = domaintest.NewPlayerBuilder(playerUUID, start.Add(45*time.Hour).Add(30*time.Minute)).WithGamesPlayed(20).WithExperience(11_900).BuildPtr()

			storePlayer(t, p, players...)

			sessions, err := p.GetSessions(ctx, playerUUID, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []domain.Session{}
			requireEqualSessions(t, expectedSessions, sessions)
		})

		t.Run("only xp change", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPlayerRepository(t, db, "get_sessions_only_xp_change")
			playerUUID := domaintest.NewUUID(t)
			start := time.Date(2024, time.March, 24, 17, 37, 14, 987_654_321, time.FixedZone("UTC", 3600*9))

			players := make([]*domain.PlayerPIT, 4)
			// Session 1
			players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(5*time.Minute)).WithGamesPlayed(16).WithExperience(9_200).BuildPtr()
			players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(30*time.Minute)).WithGamesPlayed(16).WithExperience(9_400).BuildPtr()
			// Session 2
			players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(45*time.Minute)).WithGamesPlayed(16).WithExperience(9_400).BuildPtr()
			players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(31*time.Minute)).WithGamesPlayed(16).WithExperience(10_800).BuildPtr()

			playerData := storePlayer(t, p, players...)

			sessions, err := p.GetSessions(ctx, playerUUID, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []domain.Session{
				{
					Start:       *playerData[0],
					End:         *playerData[1],
					Consecutive: true,
				},
				{
					Start:       *playerData[2],
					End:         *playerData[3],
					Consecutive: true,
				},
			}
			requireEqualSessions(t, expectedSessions, sessions)
		})

		t.Run("only games played change", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPlayerRepository(t, db, "get_sessions_only_games_played_change")
			playerUUID := domaintest.NewUUID(t)
			start := time.Date(2024, time.August, 2, 1, 47, 34, 987_654_321, time.FixedZone("UTC", 3600*3))

			players := make([]*domain.PlayerPIT, 4)
			// Session 1
			players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(5*time.Minute)).WithGamesPlayed(16).WithExperience(9_200).BuildPtr()
			players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(30*time.Minute)).WithGamesPlayed(17).WithExperience(9_200).BuildPtr()
			// Session 2
			players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(45*time.Minute)).WithGamesPlayed(17).WithExperience(9_200).BuildPtr()
			players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(31*time.Minute)).WithGamesPlayed(18).WithExperience(9_200).BuildPtr()

			playerData := storePlayer(t, p, players...)

			sessions, err := p.GetSessions(ctx, playerUUID, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []domain.Session{
				{
					Start:       *playerData[0],
					End:         *playerData[1],
					Consecutive: true,
				},
				{
					Start:       *playerData[2],
					End:         *playerData[3],
					Consecutive: true,
				},
			}
			requireEqualSessions(t, expectedSessions, sessions)
		})

		t.Run("gaps in sessions", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPlayerRepository(t, db, "get_sessions_gaps_in_sessions")
			playerUUID := domaintest.NewUUID(t)
			start := time.Date(2022, time.November, 2, 13, 47, 34, 987_654_321, time.FixedZone("UTC", 3600*3))

			// Players not using the overlay, but getting queued by players using the overlay will have sporadic stat distributions
			// Their actual session may be split into multiple single stat entries, some of which may be
			// close enough together to be considered a single session. This can result in one actual session
			// turning into mulitple calculated sessions.
			players := make([]*domain.PlayerPIT, 10)

			players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(5*time.Minute)).WithGamesPlayed(16).WithExperience(9_200).BuildPtr()
			players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(30*time.Minute)).WithGamesPlayed(17).WithExperience(9_200).BuildPtr()

			players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(45*time.Minute)).WithGamesPlayed(20).WithExperience(15_200).BuildPtr()

			players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(5*time.Hour).Add(45*time.Minute)).WithGamesPlayed(23).WithExperience(17_200).BuildPtr()

			players[4] = domaintest.NewPlayerBuilder(playerUUID, start.Add(7*time.Hour).Add(45*time.Minute)).WithGamesPlayed(27).WithExperience(19_200).BuildPtr()
			players[5] = domaintest.NewPlayerBuilder(playerUUID, start.Add(7*time.Hour).Add(55*time.Minute)).WithGamesPlayed(28).WithExperience(19_800).BuildPtr()

			players[6] = domaintest.NewPlayerBuilder(playerUUID, start.Add(9*time.Hour).Add(15*time.Minute)).WithGamesPlayed(30).WithExperience(20_800).BuildPtr()
			players[7] = domaintest.NewPlayerBuilder(playerUUID, start.Add(9*time.Hour).Add(55*time.Minute)).WithGamesPlayed(33).WithExperience(23_800).BuildPtr()

			players[8] = domaintest.NewPlayerBuilder(playerUUID, start.Add(11*time.Hour).Add(15*time.Minute)).WithGamesPlayed(35).WithExperience(28_800).BuildPtr()

			players[9] = domaintest.NewPlayerBuilder(playerUUID, start.Add(17*time.Hour).Add(15*time.Minute)).WithGamesPlayed(44).WithExperience(38_800).BuildPtr()

			playerData := storePlayer(t, p, players...)

			sessions, err := p.GetSessions(ctx, playerUUID, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []domain.Session{
				{
					Start:       *playerData[0],
					End:         *playerData[1],
					Consecutive: true,
				},
				{
					Start:       *playerData[4],
					End:         *playerData[5],
					Consecutive: true,
				},
				{
					Start:       *playerData[6],
					End:         *playerData[7],
					Consecutive: false,
				},
			}
			requireEqualSessions(t, expectedSessions, sessions)
		})

		t.Run("end", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPlayerRepository(t, db, "end")
			playerUUID := domaintest.NewUUID(t)
			start := time.Date(2025, time.December, 9, 14, 13, 34, 987_654_321, time.FixedZone("UTC", 3600*0))

			players := make([]*domain.PlayerPIT, 3)
			players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(23*time.Hour).Add(5*time.Minute)).WithGamesPlayed(16).WithExperience(9_200).BuildPtr()
			players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(23*time.Hour).Add(40*time.Minute)).WithGamesPlayed(17).WithExperience(9_500).BuildPtr()
			players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(24*time.Hour).Add(05*time.Minute)).WithGamesPlayed(18).WithExperience(9_900).BuildPtr()

			playerData := storePlayer(t, p, players...)

			sessions, err := p.GetSessions(ctx, playerUUID, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []domain.Session{
				{
					Start:       *playerData[0],
					End:         *playerData[2],
					Consecutive: true,
				},
			}
			requireEqualSessions(t, expectedSessions, sessions)
		})

		t.Run("mostly consecutive", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPlayerRepository(t, db, "mostly_consecutive")
			playerUUID := domaintest.NewUUID(t)
			start := time.Date(2025, time.February, 7, 4, 13, 34, 987_654_321, time.FixedZone("UTC", 3600*-10))

			players := make([]*domain.PlayerPIT, 6)
			players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(5*time.Minute)).WithGamesPlayed(15).WithExperience(9_200).BuildPtr()
			players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(40*time.Minute)).WithGamesPlayed(16).WithExperience(9_500).BuildPtr()
			players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour).Add(05*time.Minute)).WithGamesPlayed(17).WithExperience(9_900).BuildPtr()
			players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour).Add(45*time.Minute)).WithGamesPlayed(20).WithExperience(10_900).BuildPtr()
			players[4] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour).Add(55*time.Minute)).WithGamesPlayed(21).WithExperience(11_900).BuildPtr()
			players[5] = domaintest.NewPlayerBuilder(playerUUID, start.Add(5*time.Hour).Add(15*time.Minute)).WithGamesPlayed(22).WithExperience(12_900).BuildPtr()

			playerData := storePlayer(t, p, players...)

			sessions, err := p.GetSessions(ctx, playerUUID, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []domain.Session{
				{
					Start:       *playerData[0],
					End:         *playerData[5],
					Consecutive: false,
				},
			}
			requireEqualSessions(t, expectedSessions, sessions)
		})

		t.Run("short pauses", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPlayerRepository(t, db, "short_pauses")
			playerUUID := domaintest.NewUUID(t)
			start := time.Date(2025, time.December, 1, 7, 13, 34, 987_654_321, time.FixedZone("UTC", 3600*7))

			players := make([]*domain.PlayerPIT, 6)
			players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(5*time.Minute)).WithGamesPlayed(16).WithExperience(9_200).BuildPtr()
			players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Hour).Add(40*time.Minute)).WithGamesPlayed(16).WithExperience(9_500).BuildPtr()
			players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(05*time.Minute)).WithGamesPlayed(16).WithExperience(9_600).BuildPtr()
			players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(45*time.Minute)).WithGamesPlayed(17).WithExperience(10_900).BuildPtr()
			players[4] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour).Add(55*time.Minute)).WithGamesPlayed(17).WithExperience(10_900).BuildPtr()
			players[5] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(15*time.Minute)).WithGamesPlayed(17).WithExperience(11_900).BuildPtr()

			playerData := storePlayer(t, p, players...)

			sessions, err := p.GetSessions(ctx, playerUUID, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []domain.Session{
				{
					Start:       *playerData[0],
					End:         *playerData[5],
					Consecutive: true,
				},
			}
			requireEqualSessions(t, expectedSessions, sessions)
		})

		t.Run("2 gap -> still consecutive", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPlayerRepository(t, db, "two_gap_still_consecutive")
			playerUUID := domaintest.NewUUID(t)
			start := time.Date(2025, time.February, 7, 4, 13, 34, 987_654_321, time.FixedZone("UTC", 3600*-10))

			players := make([]*domain.PlayerPIT, 6)
			players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(5*time.Minute)).WithGamesPlayed(16).WithExperience(9_200).BuildPtr()
			players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour).Add(40*time.Minute)).WithGamesPlayed(17).WithExperience(9_500).BuildPtr()
			players[2] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour).Add(05*time.Minute)).WithGamesPlayed(18).WithExperience(9_900).BuildPtr()
			players[3] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour).Add(45*time.Minute)).WithGamesPlayed(20).WithExperience(10_900).BuildPtr()
			players[4] = domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour).Add(55*time.Minute)).WithGamesPlayed(21).WithExperience(11_900).BuildPtr()
			players[5] = domaintest.NewPlayerBuilder(playerUUID, start.Add(5*time.Hour).Add(15*time.Minute)).WithGamesPlayed(22).WithExperience(12_900).BuildPtr()

			playerData := storePlayer(t, p, players...)

			sessions, err := p.GetSessions(ctx, playerUUID, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []domain.Session{
				{
					Start:       *playerData[0],
					End:         *playerData[5],
					Consecutive: true,
				},
			}
			requireEqualSessions(t, expectedSessions, sessions)
		})

		t.Run("returns db ids", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPlayerRepository(t, db, "returns_db_ids")
			playerUUID := domaintest.NewUUID(t)
			start := time.Date(2026, time.February, 16, 4, 13, 34, 987_654_321, time.FixedZone("UTC", 3600*-11))

			players := make([]*domain.PlayerPIT, 2)
			players[0] = domaintest.NewPlayerBuilder(playerUUID, start.Add(1*time.Minute)).WithGamesPlayed(16).WithExperience(9_200).BuildPtr()
			players[1] = domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Minute)).WithGamesPlayed(17).WithExperience(10_200).BuildPtr()

			playerData := storePlayer(t, p, players...)

			sessions, err := p.GetSessions(ctx, playerUUID, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []domain.Session{
				{
					Start:       *playerData[0],
					End:         *playerData[1],
					Consecutive: true,
				},
			}
			requireEqualSessions(t, expectedSessions, sessions)

			requireValidDBID(t, sessions[0].Start.DBID)
			requireValidDBID(t, sessions[0].End.DBID)
		})
	})

	t.Run("FindMilestoneAchievements", func(t *testing.T) {
		t.Parallel()

		storePlayers := func(t *testing.T, p PlayerRepository, players ...*domain.PlayerPIT) []*domain.PlayerPIT {
			t.Helper()
			playerData := make([]*domain.PlayerPIT, len(players))
			for i, player := range players {
				err := p.StorePlayer(ctx, player)
				require.NoError(t, err)

				// Assert creation succeeded
				history, err := p.GetHistory(ctx, player.UUID, player.QueriedAt, player.QueriedAt.Add(1*time.Microsecond), 2)
				require.NoError(t, err)
				require.Len(t, history, 1)

				playerData[i] = &history[0]
			}
			return playerData
		}

		playerUUID := domaintest.NewUUID(t)

		t.Run("GamemodeOverall and StatExperience", func(t *testing.T) {
			t.Parallel()

			tests := []struct {
				name       string
				players    []*domain.PlayerPIT
				milestones []int64
				expected   []domain.MilestoneAchievement
			}{
				{
					name: "Single milestone reached",
					players: []*domain.PlayerPIT{
						domaintest.NewPlayerBuilder(playerUUID, time.Date(2021, time.January, 1, 12, 0, 0, 0, time.UTC)).WithExperience(500).BuildPtr(),
						domaintest.NewPlayerBuilder(playerUUID, time.Date(2021, time.January, 2, 12, 0, 0, 0, time.UTC)).WithExperience(1000).BuildPtr(),
						domaintest.NewPlayerBuilder(playerUUID, time.Date(2021, time.January, 3, 12, 0, 0, 0, time.UTC)).WithExperience(1500).BuildPtr(),
					},
					milestones: []int64{1200},
					expected: []domain.MilestoneAchievement{
						{
							Milestone: 1200,
							After: &domain.MilestoneAchievementStats{
								Player: domaintest.NewPlayerBuilder(playerUUID, time.Date(2021, time.January, 3, 12, 0, 0, 0, time.UTC)).WithExperience(1500).Build(),
								Value:  1500,
							},
						},
					},
				},
				{
					name: "Multiple milestones reached",
					players: []*domain.PlayerPIT{
						domaintest.NewPlayerBuilder(playerUUID, time.Date(2021, time.January, 1, 12, 0, 0, 0, time.UTC)).WithExperience(500).BuildPtr(),
						domaintest.NewPlayerBuilder(playerUUID, time.Date(2021, time.January, 2, 12, 0, 0, 0, time.UTC)).WithExperience(1000).BuildPtr(),
						domaintest.NewPlayerBuilder(playerUUID, time.Date(2021, time.January, 3, 12, 0, 0, 0, time.UTC)).WithExperience(2000).BuildPtr(),
						domaintest.NewPlayerBuilder(playerUUID, time.Date(2021, time.January, 4, 12, 0, 0, 0, time.UTC)).WithExperience(3000).BuildPtr(),
					},
					milestones: []int64{800, 1500, 2500},
					expected: []domain.MilestoneAchievement{
						{
							Milestone: 800,
							After: &domain.MilestoneAchievementStats{
								Player: domaintest.NewPlayerBuilder(playerUUID, time.Date(2021, time.January, 2, 12, 0, 0, 0, time.UTC)).WithExperience(1000).Build(),
								Value:  1000,
							},
						},
						{
							Milestone: 1500,
							After: &domain.MilestoneAchievementStats{
								Player: domaintest.NewPlayerBuilder(playerUUID, time.Date(2021, time.January, 3, 12, 0, 0, 0, time.UTC)).WithExperience(2000).Build(),
								Value:  2000,
							},
						},
						{
							Milestone: 2500,
							After: &domain.MilestoneAchievementStats{
								Player: domaintest.NewPlayerBuilder(playerUUID, time.Date(2021, time.January, 4, 12, 0, 0, 0, time.UTC)).WithExperience(3000).Build(),
								Value:  3000,
							},
						},
					},
				},
				{
					name: "No milestones reached",
					players: []*domain.PlayerPIT{
						domaintest.NewPlayerBuilder(playerUUID, time.Date(2021, time.January, 1, 12, 0, 0, 0, time.UTC)).WithExperience(500).BuildPtr(),
						domaintest.NewPlayerBuilder(playerUUID, time.Date(2021, time.January, 2, 12, 0, 0, 0, time.UTC)).WithExperience(600).BuildPtr(),
					},
					milestones: []int64{1000, 2000},
					expected:   []domain.MilestoneAchievement{},
				},
				{
					name: "Milestones skipped",
					players: []*domain.PlayerPIT{
						domaintest.NewPlayerBuilder(playerUUID, time.Date(2021, time.January, 1, 12, 0, 0, 0, time.UTC)).WithExperience(500).BuildPtr(),
						domaintest.NewPlayerBuilder(playerUUID, time.Date(2021, time.January, 2, 12, 0, 0, 0, time.UTC)).WithExperience(10_000).BuildPtr(),
						domaintest.NewPlayerBuilder(playerUUID, time.Date(2021, time.January, 3, 12, 0, 0, 0, time.UTC)).WithExperience(11_000).BuildPtr(),
					},
					milestones: []int64{1_000, 5_000, 8_000, 12_000},
					expected: []domain.MilestoneAchievement{
						{
							Milestone: 8_000,
							After: &domain.MilestoneAchievementStats{
								Player: domaintest.NewPlayerBuilder(playerUUID, time.Date(2021, time.January, 2, 12, 0, 0, 0, time.UTC)).WithExperience(10_000).Build(),
								Value:  10_000,
							},
						},
					},
				},
				{
					name: "Milestones skipped - final reached",
					players: []*domain.PlayerPIT{
						domaintest.NewPlayerBuilder(playerUUID, time.Date(2021, time.January, 1, 12, 0, 0, 0, time.UTC)).WithExperience(500).BuildPtr(),
						domaintest.NewPlayerBuilder(playerUUID, time.Date(2021, time.January, 2, 12, 0, 0, 0, time.UTC)).WithExperience(100_000).BuildPtr(),
						domaintest.NewPlayerBuilder(playerUUID, time.Date(2021, time.January, 3, 12, 0, 0, 0, time.UTC)).WithExperience(200_000).BuildPtr(),
					},
					milestones: []int64{1_000, 5_000, 8_000, 12_000},
					expected: []domain.MilestoneAchievement{
						{
							Milestone: 12_000,
							After: &domain.MilestoneAchievementStats{
								Player: domaintest.NewPlayerBuilder(playerUUID, time.Date(2021, time.January, 2, 12, 0, 0, 0, time.UTC)).WithExperience(100_000).Build(),
								Value:  100_000,
							},
						},
					},
				},
				{
					name: "Multiple sets of milestones skipped",
					players: []*domain.PlayerPIT{
						domaintest.NewPlayerBuilder(playerUUID, time.Date(2025, time.March, 1, 19, 0, 0, 0, time.UTC)).WithExperience(1_000).BuildPtr(),
						domaintest.NewPlayerBuilder(playerUUID, time.Date(2025, time.March, 2, 19, 0, 0, 0, time.UTC)).WithExperience(6_001).BuildPtr(),
					},
					milestones: []int64{500, 600, 700, 800, 900, 1_000, 2_000, 3_000, 4_000, 5_000, 6_000, 7_000, 8_000, 9_000, 10_000},
					expected: []domain.MilestoneAchievement{
						{
							Milestone: 1_000,
							After: &domain.MilestoneAchievementStats{
								Player: domaintest.NewPlayerBuilder(playerUUID, time.Date(2025, time.March, 1, 19, 0, 0, 0, time.UTC)).WithExperience(1_000).Build(),
								Value:  1_000,
							},
						},
						{
							Milestone: 6_000,
							After: &domain.MilestoneAchievementStats{
								Player: domaintest.NewPlayerBuilder(playerUUID, time.Date(2025, time.March, 2, 19, 0, 0, 0, time.UTC)).WithExperience(6_001).Build(),
								Value:  6_001,
							},
						},
					},
				},
			}

			for _, tt := range tests {
				t.Run(tt.name, func(t *testing.T) {
					t.Parallel()
					p := newPostgresPlayerRepository(t, db, fmt.Sprintf("find_milestone_%s", strings.ReplaceAll(tt.name, " ", "_")))

					storePlayers(t, p, tt.players...)

					achievements, err := p.FindMilestoneAchievements(ctx, playerUUID, domain.GamemodeOverall, domain.StatExperience, tt.milestones)
					require.NoError(t, err)

					for _, achievement := range achievements {
						if achievement.After == nil {
							continue
						}
						// Ensure UTC for comparison
						achievement.After.Player.QueriedAt = achievement.After.Player.QueriedAt.UTC()

						// Drop db id for comparison
						requireValidDBID(t, achievement.After.Player.DBID)
						achievement.After.Player.DBID = nil
					}

					// Lazy json compare
					achievementsJSON, err := json.MarshalIndent(achievements, "", "  ")
					require.NoError(t, err)
					expectedJSON, err := json.MarshalIndent(tt.expected, "", "  ")
					require.NoError(t, err)
					require.JSONEq(t, string(expectedJSON), string(achievementsJSON))
				})
			}
		})

		t.Run("Unsupported gamemode", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPlayerRepository(t, db, "find_milestone_unsupported_gamemode")
			playerUUID := domaintest.NewUUID(t)

			_, err := p.FindMilestoneAchievements(ctx, playerUUID, domain.Gamemode("UNSUPPORTED"), domain.StatExperience, []int64{1000})
			require.Error(t, err)
			require.Contains(t, err.Error(), "only overall gamemode is supported")
		})

		t.Run("Unsupported stat", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPlayerRepository(t, db, "find_milestone_unsupported_stat")
			playerUUID := domaintest.NewUUID(t)

			_, err := p.FindMilestoneAchievements(ctx, playerUUID, domain.GamemodeOverall, domain.Stat("UNSUPPORTED"), []int64{1000})
			require.Error(t, err)
			require.Contains(t, err.Error(), "only experience stat is supported")
		})

		t.Run("Empty milestones", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPlayerRepository(t, db, "find_milestone_empty")
			playerUUID := domaintest.NewUUID(t)

			achievements, err := p.FindMilestoneAchievements(ctx, playerUUID, domain.GamemodeOverall, domain.StatExperience, []int64{})
			require.NoError(t, err)
			require.Empty(t, achievements)
		})

		t.Run("Invalid UUID", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPlayerRepository(t, db, "find_milestone_invalid_uuid")

			_, err := p.FindMilestoneAchievements(ctx, "invalid-uuid", domain.GamemodeOverall, domain.StatExperience, []int64{1000})
			require.Error(t, err)
			require.Contains(t, err.Error(), "uuid is not normalized")
		})
	})
}
