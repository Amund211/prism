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

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/strutils"
)

func newPlayerPIT(uuid string, value int, queriedAt time.Time) *domain.PlayerPIT {
	stats := domain.GamemodeStatsPIT{
		Kills: value,
	}
	return &domain.PlayerPIT{
		QueriedAt: queriedAt,

		UUID: uuid,

		Solo:    stats,
		Doubles: stats,
		Threes:  stats,
		Fours:   stats,
		Overall: stats,
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

			uuid := newUUID(t)
			player := newPlayerPIT(uuid, 0, now)

			requireNotStored(t, player)
			err := p.StoreStats(ctx, player)
			require.NoError(t, err)
			requireStoredOnce(t, player)
		})

		t.Run("store multiple for same user", func(t *testing.T) {
			t.Parallel()
			player_uuid := newUUID(t)
			t1 := now
			t2 := t1.Add(3 * time.Minute)

			player1 := newPlayerPIT(player_uuid, 1, t1)
			player2 := newPlayerPIT(player_uuid, 2, t2)

			requireNotStored(t, player1)
			err := p.StoreStats(ctx, player1)
			require.NoError(t, err)
			requireStoredOnce(t, player1)

			requireNotStored(t, player2)
			err = p.StoreStats(ctx, player2)
			require.NoError(t, err)
			requireStoredOnce(t, player2)

			// We never stored these combinations
			player1t2 := newPlayerPIT(player_uuid, 1, t2)
			requireNotStored(t, player1t2)
			player2t1 := newPlayerPIT(player_uuid, 2, t1)
			requireNotStored(t, player2t1)
		})

		t.Run("stats are not stored within one minute", func(t *testing.T) {
			t.Parallel()
			player_uuid := newUUID(t)
			t1 := now

			player1 := newPlayerPIT(player_uuid, 1, t1)

			requireNotStored(t, player1)
			err := p.StoreStats(ctx, player1)
			require.NoError(t, err)
			requireStoredOnce(t, player1)

			for i := 0; i < 60; i++ {
				t2 := t1.Add(time.Duration(i) * time.Second)
				player2 := newPlayerPIT(player_uuid, 2, t2)

				requireNotStored(t, player2)
				err = p.StoreStats(ctx, player2)
				require.NoError(t, err)
				requireNotStored(t, player2)
			}
		})

		t.Run("consecutive duplicate stats are not stored", func(t *testing.T) {
			t.Parallel()
			player_uuid := newUUID(t)

			t1 := now
			player1 := newPlayerPIT(player_uuid, 1, t1)

			requireNotStored(t, player1)
			err := p.StoreStats(ctx, player1)
			require.NoError(t, err)
			requireStoredOnce(t, player1)

			for i := 1; i < 60; i++ {
				t2 := t1.Add(time.Duration(i) * time.Minute)
				player2 := newPlayerPIT(player_uuid, 1, t2)
				requireNotStored(t, player2)
				err = p.StoreStats(ctx, player2)
				require.NoError(t, err)
				requireNotStored(t, player2)
			}
		})

		t.Run("consecutive duplicate stats are stored if an hour or more apart", func(t *testing.T) {
			t.Parallel()
			player_uuid := newUUID(t)

			t1 := now
			player1 := newPlayerPIT(player_uuid, 1, t1)

			requireNotStored(t, player1)
			err := p.StoreStats(ctx, player1)
			require.NoError(t, err)
			requireStoredOnce(t, player1)

			// Consecutive duplicate data is more than an hour old -> store this one
			t2 := t1.Add(1 * time.Hour)
			player2 := newPlayerPIT(player_uuid, 1, t2)

			err = p.StoreStats(ctx, player2)
			require.NoError(t, err)
			requireStoredOnce(t, player2)
		})

		t.Run("non-consecutive duplicate stats are stored", func(t *testing.T) {
			t.Parallel()
			player_uuid := newUUID(t)

			t1 := now
			player1 := newPlayerPIT(player_uuid, 1, t1)

			requireNotStored(t, player1)
			err := p.StoreStats(ctx, player1)
			require.NoError(t, err)
			requireStoredOnce(t, player1)

			t2 := t1.Add(2 * time.Minute)
			player2 := newPlayerPIT(player_uuid, 2, t2)

			requireNotStored(t, player2)
			err = p.StoreStats(ctx, player2)
			require.NoError(t, err)
			requireStoredOnce(t, player2)

			// Old duplicate data is not consecutive any more -> store it
			t3 := t2.Add(2 * time.Minute)
			player3 := newPlayerPIT(player_uuid, 1, t3)
			requireNotStored(t, player3)
			err = p.StoreStats(ctx, player3)
			require.NoError(t, err)
			requireStoredOnce(t, player3)
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
			player2 := newPlayerPIT(player_uuid, 1, t2)
			err = p.StoreStats(ctx, player2)
			require.NoError(t, err)
			requireStoredOnce(t, player2)
		})

		t.Run("same data for multiple users", func(t *testing.T) {
			t.Parallel()
			t1 := now
			uuid1 := newUUID(t)
			uuid2 := newUUID(t)
			player1 := newPlayerPIT(uuid1, 3, t1)
			player2 := newPlayerPIT(uuid2, 3, t1)

			requireNotStored(t, player1)
			err := p.StoreStats(ctx, player1)
			require.NoError(t, err)
			requireStoredOnce(t, player1)

			requireNotStored(t, player2)
			err = p.StoreStats(ctx, player2)
			require.NoError(t, err)
			requireStoredOnce(t, player2)

			requireStoredOnce(t, player1)
		})

		t.Run("store nil player fails", func(t *testing.T) {
			t.Parallel()
			err := p.StoreStats(ctx, nil)
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
					player := newPlayerPIT(uuid, i, t1)

					err := p.StoreStats(ctx, player)
					require.NoError(t, err)
					requireStoredOnce(t, player)
				}
			})
			t.Run("when storing for the same player at the same time", func(t *testing.T) {
				t.Parallel()
				uuid := newUUID(t)
				t1 := now
				player := newPlayerPIT(uuid, 1, t1)

				for i := 0; i < limit; i++ {
					err := p.StoreStats(ctx, player)
					require.NoError(t, err)
					// Will only ever be stored once since the time is within one minute
					requireStoredOnce(t, player)
				}
			})
		})
	})

	t.Run("GetHistory", func(t *testing.T) {
		t.Parallel()

		storeStats := func(t *testing.T, p *PostgresStatsPersistor, players ...*domain.PlayerPIT) {
			t.Helper()
			for _, player := range players {
				err := p.StoreStats(ctx, player)
				require.NoError(t, err)
			}
		}

		setStoredStats := func(t *testing.T, p *PostgresStatsPersistor, players ...*domain.PlayerPIT) {
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

			storeStats(t, p, players...)

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
			p := newPostgresPersistor(t, db, "get_history_evenly_spread_across_a_day")
			janFirst21 := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", 3600*10))

			player_uuid := newUUID(t)

			players := []*domain.PlayerPIT{}
			density := 4
			count := 24 * density
			interval := 24 * time.Hour / time.Duration(count)
			// Evenly distributed stats for 24 hours + 1 extra
			for i := 0; i < count+1; i++ {
				players = append(
					players,
					newPlayerPIT(player_uuid, i, janFirst21.Add(time.Duration(i)*interval)),
				)
			}

			require.Len(t, players, 24*4+1)

			setStoredStats(t, p, players...)

			history, err := p.GetHistory(ctx, player_uuid, janFirst21, janFirst21.Add(24*time.Hour), 48)
			require.NoError(t, err)
			expectedDistribution := []time.Time{}
			for i := 0; i < 24; i++ {
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
			p := newPostgresPersistor(t, db, "get_history_random_clusters")
			player_uuid := newUUID(t)
			start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*8))

			players := make([]*domain.PlayerPIT, 13)
			// Before start
			players[0] = newPlayerPIT(player_uuid, 0, start.Add(0*time.Hour).Add(-1*time.Minute))

			// First 30 min interval
			players[1] = newPlayerPIT(player_uuid, 1, start.Add(0*time.Hour).Add(7*time.Minute))
			players[2] = newPlayerPIT(player_uuid, 2, start.Add(0*time.Hour).Add(17*time.Minute))

			// Second 30 min interval
			players[3] = newPlayerPIT(player_uuid, 3, start.Add(0*time.Hour).Add(37*time.Minute))

			// Sixth 30 min interval
			players[4] = newPlayerPIT(player_uuid, 4, start.Add(2*time.Hour).Add(40*time.Minute))
			players[5] = newPlayerPIT(player_uuid, 5, start.Add(2*time.Hour).Add(45*time.Minute))
			players[6] = newPlayerPIT(player_uuid, 6, start.Add(2*time.Hour).Add(50*time.Minute))
			players[7] = newPlayerPIT(player_uuid, 7, start.Add(2*time.Hour).Add(55*time.Minute))

			// Seventh 30 min interval
			players[8] = newPlayerPIT(player_uuid, 8, start.Add(3*time.Hour).Add(1*time.Minute))

			// Eighth 30 min interval
			players[9] = newPlayerPIT(player_uuid, 9, start.Add(3*time.Hour).Add(47*time.Minute))
			players[10] = newPlayerPIT(player_uuid, 10, start.Add(3*time.Hour).Add(59*time.Minute))

			// After end
			players[11] = newPlayerPIT(player_uuid, 11, start.Add(4*time.Hour).Add(1*time.Minute))
			players[12] = newPlayerPIT(player_uuid, 12, start.Add(4000*time.Hour).Add(1*time.Minute))

			setStoredStats(t, p, players...)

			// Get entries at the start and end of each 30 min interval (8 in total)
			history, err := p.GetHistory(ctx, player_uuid, start, start.Add(4*time.Hour), 16)
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

				require.Equal(t, player_uuid, expectedPIT.UUID)
				require.Equal(t, player_uuid, playerPIT.UUID)

				// Mock data matches
				require.Equal(t, expectedPIT.Overall.Kills, playerPIT.Overall.Kills)

				require.WithinDuration(t, expectedPIT.QueriedAt, playerPIT.QueriedAt, 0)
			}
		})

		t.Run("no duplicates returned", func(t *testing.T) {
			// The current implementation gets both the first and last stats in each interval
			// Make sure these are not the same instance.

			t.Parallel()
			p := newPostgresPersistor(t, db, "no_duplicates_returned")

			t.Run("single stat stored", func(t *testing.T) {
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
							player_uuid := newUUID(t)
							players := []*domain.PlayerPIT{
								newPlayerPIT(player_uuid, 1, queriedAt),
							}

							storeStats(t, p, players...)

							history, err := p.GetHistory(ctx, player_uuid, start, end, limit)
							require.NoError(t, err)

							require.Len(t, history, 1)

							expectedPIT := players[0]
							playerPIT := history[0]

							require.Equal(t, player_uuid, expectedPIT.UUID)
							require.Equal(t, player_uuid, playerPIT.UUID)

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
						player_uuid := newUUID(t)
						players := []*domain.PlayerPIT{
							newPlayerPIT(player_uuid, 1, start.Add(time.Minute)),
							newPlayerPIT(player_uuid, 10, end.Add(-1*time.Minute)),
						}

						storeStats(t, p, players...)

						history, err := p.GetHistory(ctx, player_uuid, start, end, limit)
						require.NoError(t, err)

						require.Len(t, history, 2)

						for i, expectedPIT := range players {
							playerPIT := history[i]

							require.Equal(t, player_uuid, expectedPIT.UUID)
							require.Equal(t, player_uuid, playerPIT.UUID)

							// Mock data matches
							require.Equal(t, expectedPIT.Overall.Kills, playerPIT.Overall.Kills)

							require.WithinDuration(t, expectedPIT.QueriedAt, playerPIT.QueriedAt, 0)
						}
					})
				}
			})
		})
	})

	t.Run("GetSessions", func(t *testing.T) {
		t.Parallel()
		storeStats := func(t *testing.T, p *PostgresStatsPersistor, players ...*domain.PlayerPIT) []*domain.PlayerPIT {
			t.Helper()
			playerData := make([]*domain.PlayerPIT, len(players))
			for i, player := range players {
				// Add a random number to prevent de-duplication of the stored stats
				player.Solo.Winstreak = &i
				err := p.StoreStats(ctx, player)
				require.NoError(t, err)

				history, err := p.GetHistory(ctx, player.UUID, player.QueriedAt, player.QueriedAt.Add(1*time.Microsecond), 2)
				require.NoError(t, err)
				require.Len(t, history, 1)
				playerData[i] = &history[0]
			}
			return playerData
		}

		newPlayer := func(uuid string, gamesPlayed int, exp float64, queriedAt time.Time) *domain.PlayerPIT {
			return &domain.PlayerPIT{
				QueriedAt:  queriedAt,
				UUID:       uuid,
				Experience: exp,
				Overall: domain.GamemodeStatsPIT{
					GamesPlayed: gamesPlayed,
				},
			}
		}

		requireEqualSessions := func(t *testing.T, expected, actual []Session) {
			t.Helper()

			type normalizedPlayerPIT struct {
				queriedAtISO  string
				uuid          string
				experience    float64
				gamesPlayed   int
				soloWinstreak int
			}

			type normalizedSession struct {
				start normalizedPlayerPIT
				end   normalizedPlayerPIT
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

			expectedNormalized := make([]normalizedSession, len(expected))
			for i, session := range expected {
				expectedNormalized[i] = normalizedSession{
					start: normalizePlayerData(&session.Start),
					end:   normalizePlayerData(&session.End),
				}
			}

			actualNormalized := make([]normalizedSession, len(actual))
			for i, session := range actual {
				actualNormalized[i] = normalizedSession{
					start: normalizePlayerData(&session.Start),
					end:   normalizePlayerData(&session.End),
				}
			}
			require.Equal(t, expectedNormalized, actualNormalized)
		}

		t.Run("random clusters", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPersistor(t, db, "get_sessions_random_clusters")
			player_uuid := newUUID(t)
			start := time.Date(2022, time.February, 14, 0, 0, 0, 0, time.FixedZone("UTC", 3600*1))

			players := make([]*domain.PlayerPIT, 26)
			// Ended session befor the start
			players[0] = newPlayer(player_uuid, 10, 1_000, start.Add(-8*time.Hour).Add(-1*time.Minute))
			players[1] = newPlayer(player_uuid, 11, 1_300, start.Add(-8*time.Hour).Add(7*time.Minute))
			players[2] = newPlayer(player_uuid, 12, 1_600, start.Add(-8*time.Hour).Add(17*time.Minute))

			// Session starting just before the start
			// Some inactivity at the start of the session
			players[3] = newPlayer(player_uuid, 12, 1_600, start.Add(0*time.Hour).Add(-37*time.Minute))
			players[4] = newPlayer(player_uuid, 12, 1_600, start.Add(0*time.Hour).Add(-27*time.Minute))
			players[5] = newPlayer(player_uuid, 12, 1_600, start.Add(0*time.Hour).Add(-17*time.Minute))
			players[6] = newPlayer(player_uuid, 13, 1_900, start.Add(0*time.Hour).Add(-12*time.Minute))
			players[7] = newPlayer(player_uuid, 14, 2_200, start.Add(0*time.Hour).Add(2*time.Minute))
			// One hour space between entries
			players[8] = newPlayer(player_uuid, 15, 7_200, start.Add(0*time.Hour).Add(38*time.Minute))
			players[9] = newPlayer(player_uuid, 16, 7_900, start.Add(1*time.Hour).Add(38*time.Minute))
			// One hour space between stat change, with some inactivity events in between
			players[10] = newPlayer(player_uuid, 17, 8_900, start.Add(1*time.Hour).Add(45*time.Minute))
			players[11] = newPlayer(player_uuid, 17, 8_900, start.Add(1*time.Hour).Add(55*time.Minute))
			players[12] = newPlayer(player_uuid, 17, 8_900, start.Add(2*time.Hour).Add(5*time.Minute))
			players[13] = newPlayer(player_uuid, 17, 8_900, start.Add(2*time.Hour).Add(15*time.Minute))
			players[14] = newPlayer(player_uuid, 17, 8_900, start.Add(2*time.Hour).Add(25*time.Minute))
			players[15] = newPlayer(player_uuid, 17, 8_900, start.Add(2*time.Hour).Add(35*time.Minute))
			players[16] = newPlayer(player_uuid, 18, 9_500, start.Add(2*time.Hour).Add(45*time.Minute))
			// Some inactivity at the end
			players[17] = newPlayer(player_uuid, 18, 9_500, start.Add(2*time.Hour).Add(55*time.Minute))
			players[18] = newPlayer(player_uuid, 18, 9_500, start.Add(3*time.Hour).Add(5*time.Minute))
			players[19] = newPlayer(player_uuid, 18, 9_500, start.Add(3*time.Hour).Add(15*time.Minute))
			players[20] = newPlayer(player_uuid, 18, 9_500, start.Add(3*time.Hour).Add(25*time.Minute))
			players[21] = newPlayer(player_uuid, 18, 9_500, start.Add(3*time.Hour).Add(35*time.Minute))
			players[22] = newPlayer(player_uuid, 18, 9_500, start.Add(3*time.Hour).Add(45*time.Minute))
			players[23] = newPlayer(player_uuid, 18, 9_500, start.Add(3*time.Hour).Add(55*time.Minute))

			// New activity 71 minutues after the last entry -> new session
			players[24] = newPlayer(player_uuid, 18, 9_500, start.Add(3*time.Hour).Add(56*time.Minute))
			players[25] = newPlayer(player_uuid, 19, 10_800, start.Add(4*time.Hour).Add(16*time.Minute))

			playerData := storeStats(t, p, players...)

			sessions, err := p.GetSessions(ctx, player_uuid, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []Session{
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
			p := newPostgresPersistor(t, db, "get_sessions_single")
			player_uuid := newUUID(t)
			start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*8))

			players := make([]*domain.PlayerPIT, 1)
			players[0] = newPlayer(player_uuid, 11, 1_300, start.Add(6*time.Hour).Add(7*time.Minute))

			_ = storeStats(t, p, players...)

			sessions, err := p.GetSessions(ctx, player_uuid, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			require.Len(t, sessions, 0)
		})

		t.Run("Single stat at the start", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPersistor(t, db, "get_sessions_single_at_start")
			player_uuid := newUUID(t)
			start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*8))

			players := make([]*domain.PlayerPIT, 3)
			players[0] = newPlayer(player_uuid, 9, 1_000, start.Add(6*time.Hour).Add(7*time.Minute))

			players[1] = newPlayer(player_uuid, 10, 1_100, start.Add(8*time.Hour).Add(-1*time.Minute))
			players[2] = newPlayer(player_uuid, 11, 1_300, start.Add(8*time.Hour).Add(7*time.Minute))

			playerData := storeStats(t, p, players...)

			sessions, err := p.GetSessions(ctx, player_uuid, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []Session{
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
			p := newPostgresPersistor(t, db, "get_sessions_single_at_end")
			player_uuid := newUUID(t)
			start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*8))

			players := make([]*domain.PlayerPIT, 3)
			players[0] = newPlayer(player_uuid, 10, 1_000, start.Add(6*time.Hour).Add(-1*time.Minute))
			players[1] = newPlayer(player_uuid, 11, 1_300, start.Add(6*time.Hour).Add(7*time.Minute))

			players[2] = newPlayer(player_uuid, 12, 1_600, start.Add(8*time.Hour).Add(7*time.Minute))

			playerData := storeStats(t, p, players...)

			sessions, err := p.GetSessions(ctx, player_uuid, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []Session{
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
			p := newPostgresPersistor(t, db, "get_sessions_single_at_start_and_end")
			player_uuid := newUUID(t)
			start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*2))

			players := make([]*domain.PlayerPIT, 4)
			players[0] = newPlayer(player_uuid, 9, 1_000, start.Add(5*time.Hour).Add(7*time.Minute))

			players[1] = newPlayer(player_uuid, 10, 1_000, start.Add(8*time.Hour).Add(-1*time.Minute))
			players[2] = newPlayer(player_uuid, 11, 1_300, start.Add(8*time.Hour).Add(7*time.Minute))

			players[3] = newPlayer(player_uuid, 12, 1_600, start.Add(10*time.Hour).Add(7*time.Minute))

			playerData := storeStats(t, p, players...)

			sessions, err := p.GetSessions(ctx, player_uuid, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []Session{
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
			p := newPostgresPersistor(t, db, "get_sessions_no_stats")
			player_uuid := newUUID(t)
			start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*10))

			players := make([]*domain.PlayerPIT, 0)

			_ = storeStats(t, p, players...)

			sessions, err := p.GetSessions(ctx, player_uuid, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			require.Len(t, sessions, 0)
		})

		t.Run("inactivity between sessions", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPersistor(t, db, "get_sessions_inactivity_between_sessions")
			player_uuid := newUUID(t)
			start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*2))

			players := make([]*domain.PlayerPIT, 13)
			players[0] = newPlayer(player_uuid, 16, 9_200, start.Add(2*time.Hour).Add(30*time.Minute))
			players[1] = newPlayer(player_uuid, 16, 9_200, start.Add(2*time.Hour).Add(35*time.Minute))
			players[2] = newPlayer(player_uuid, 17, 9_400, start.Add(2*time.Hour).Add(45*time.Minute))
			players[3] = newPlayer(player_uuid, 18, 9_500, start.Add(2*time.Hour).Add(55*time.Minute))
			players[4] = newPlayer(player_uuid, 18, 9_500, start.Add(3*time.Hour).Add(5*time.Minute))
			players[5] = newPlayer(player_uuid, 18, 9_500, start.Add(3*time.Hour).Add(15*time.Minute))
			players[6] = newPlayer(player_uuid, 18, 9_500, start.Add(3*time.Hour).Add(25*time.Minute))
			players[7] = newPlayer(player_uuid, 18, 9_500, start.Add(3*time.Hour).Add(35*time.Minute))
			players[8] = newPlayer(player_uuid, 18, 9_500, start.Add(3*time.Hour).Add(45*time.Minute))
			players[9] = newPlayer(player_uuid, 18, 9_500, start.Add(3*time.Hour).Add(55*time.Minute))
			players[10] = newPlayer(player_uuid, 18, 9_500, start.Add(3*time.Hour).Add(56*time.Minute))
			players[11] = newPlayer(player_uuid, 19, 10_800, start.Add(4*time.Hour).Add(16*time.Minute))
			players[12] = newPlayer(player_uuid, 19, 10_800, start.Add(4*time.Hour).Add(20*time.Minute))

			playerData := storeStats(t, p, players...)

			sessions, err := p.GetSessions(ctx, player_uuid, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []Session{
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
			p := newPostgresPersistor(t, db, "get_sessions_1_hr_inactivity_between_sessions")
			player_uuid := newUUID(t)
			start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*2))

			players := make([]*domain.PlayerPIT, 4)
			// Session 1
			players[0] = newPlayer(player_uuid, 16, 9_200, start.Add(1*time.Hour).Add(5*time.Minute))
			players[1] = newPlayer(player_uuid, 17, 9_400, start.Add(1*time.Hour).Add(30*time.Minute))
			// Session 2
			players[2] = newPlayer(player_uuid, 17, 9_400, start.Add(1*time.Hour).Add(45*time.Minute))
			players[3] = newPlayer(player_uuid, 18, 10_800, start.Add(2*time.Hour).Add(31*time.Minute))

			playerData := storeStats(t, p, players...)

			sessions, err := p.GetSessions(ctx, player_uuid, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []Session{
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
			p := newPostgresPersistor(t, db, "get_sessions_before_and_after")
			player_uuid := newUUID(t)
			start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*2))

			players := make([]*domain.PlayerPIT, 8)
			players[0] = newPlayer(player_uuid, 16, 9_200, start.Add(-25*time.Hour).Add(5*time.Minute))
			players[1] = newPlayer(player_uuid, 17, 9_400, start.Add(-25*time.Hour).Add(30*time.Minute))

			players[2] = newPlayer(player_uuid, 17, 9_400, start.Add(-16*time.Hour).Add(5*time.Minute))
			players[3] = newPlayer(player_uuid, 18, 9_900, start.Add(-16*time.Hour).Add(30*time.Minute))

			players[4] = newPlayer(player_uuid, 18, 9_900, start.Add(25*time.Hour).Add(5*time.Minute))
			players[5] = newPlayer(player_uuid, 19, 10_900, start.Add(25*time.Hour).Add(30*time.Minute))

			players[6] = newPlayer(player_uuid, 19, 10_900, start.Add(45*time.Hour).Add(5*time.Minute))
			players[7] = newPlayer(player_uuid, 20, 11_900, start.Add(45*time.Hour).Add(30*time.Minute))

			storeStats(t, p, players...)

			sessions, err := p.GetSessions(ctx, player_uuid, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []Session{}
			requireEqualSessions(t, expectedSessions, sessions)
		})

		t.Run("only xp change", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPersistor(t, db, "get_sessions_only_xp_change")
			player_uuid := newUUID(t)
			start := time.Date(2024, time.March, 24, 17, 37, 14, 987_654_321, time.FixedZone("UTC", 3600*9))

			players := make([]*domain.PlayerPIT, 4)
			// Session 1
			players[0] = newPlayer(player_uuid, 16, 9_200, start.Add(1*time.Hour).Add(5*time.Minute))
			players[1] = newPlayer(player_uuid, 16, 9_400, start.Add(1*time.Hour).Add(30*time.Minute))
			// Session 2
			players[2] = newPlayer(player_uuid, 16, 9_400, start.Add(1*time.Hour).Add(45*time.Minute))
			players[3] = newPlayer(player_uuid, 16, 10_800, start.Add(2*time.Hour).Add(31*time.Minute))

			playerData := storeStats(t, p, players...)

			sessions, err := p.GetSessions(ctx, player_uuid, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []Session{
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
			p := newPostgresPersistor(t, db, "get_sessions_only_games_played_change")
			player_uuid := newUUID(t)
			start := time.Date(2024, time.August, 2, 1, 47, 34, 987_654_321, time.FixedZone("UTC", 3600*3))

			players := make([]*domain.PlayerPIT, 4)
			// Session 1
			players[0] = newPlayer(player_uuid, 16, 9_200, start.Add(1*time.Hour).Add(5*time.Minute))
			players[1] = newPlayer(player_uuid, 17, 9_200, start.Add(1*time.Hour).Add(30*time.Minute))
			// Session 2
			players[2] = newPlayer(player_uuid, 17, 9_200, start.Add(1*time.Hour).Add(45*time.Minute))
			players[3] = newPlayer(player_uuid, 18, 9_200, start.Add(2*time.Hour).Add(31*time.Minute))

			playerData := storeStats(t, p, players...)

			sessions, err := p.GetSessions(ctx, player_uuid, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []Session{
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
			p := newPostgresPersistor(t, db, "get_sessions_gaps_in_sessions")
			player_uuid := newUUID(t)
			start := time.Date(2022, time.November, 2, 13, 47, 34, 987_654_321, time.FixedZone("UTC", 3600*3))

			// Players not using the overlay, but getting queued by players using the overlay will have sporadic stat distributions
			// Their actual session may be split into multiple single stat entries, some of which may be
			// close enough together to be considered a single session. This can result in one actual session
			// turning into mulitple calculated sessions.
			players := make([]*domain.PlayerPIT, 10)

			players[0] = newPlayer(player_uuid, 16, 9_200, start.Add(1*time.Hour).Add(5*time.Minute))
			players[1] = newPlayer(player_uuid, 17, 9_200, start.Add(1*time.Hour).Add(30*time.Minute))

			players[2] = newPlayer(player_uuid, 20, 15_200, start.Add(3*time.Hour).Add(45*time.Minute))

			players[3] = newPlayer(player_uuid, 23, 17_200, start.Add(5*time.Hour).Add(45*time.Minute))

			players[4] = newPlayer(player_uuid, 27, 19_200, start.Add(7*time.Hour).Add(45*time.Minute))
			players[5] = newPlayer(player_uuid, 28, 19_800, start.Add(7*time.Hour).Add(55*time.Minute))

			players[6] = newPlayer(player_uuid, 30, 20_800, start.Add(9*time.Hour).Add(15*time.Minute))
			players[7] = newPlayer(player_uuid, 33, 23_800, start.Add(9*time.Hour).Add(55*time.Minute))

			players[8] = newPlayer(player_uuid, 35, 28_800, start.Add(11*time.Hour).Add(15*time.Minute))

			players[9] = newPlayer(player_uuid, 44, 38_800, start.Add(17*time.Hour).Add(15*time.Minute))

			playerData := storeStats(t, p, players...)

			sessions, err := p.GetSessions(ctx, player_uuid, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []Session{
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
			p := newPostgresPersistor(t, db, "end")
			player_uuid := newUUID(t)
			start := time.Date(2025, time.December, 9, 14, 13, 34, 987_654_321, time.FixedZone("UTC", 3600*0))

			players := make([]*domain.PlayerPIT, 3)
			players[0] = newPlayer(player_uuid, 16, 9_200, start.Add(23*time.Hour).Add(5*time.Minute))
			players[1] = newPlayer(player_uuid, 17, 9_500, start.Add(23*time.Hour).Add(40*time.Minute))
			players[2] = newPlayer(player_uuid, 18, 9_900, start.Add(24*time.Hour).Add(05*time.Minute))

			playerData := storeStats(t, p, players...)

			sessions, err := p.GetSessions(ctx, player_uuid, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []Session{
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
			p := newPostgresPersistor(t, db, "mostly_consecutive")
			player_uuid := newUUID(t)
			start := time.Date(2025, time.February, 7, 4, 13, 34, 987_654_321, time.FixedZone("UTC", 3600*-10))

			players := make([]*domain.PlayerPIT, 6)
			players[0] = newPlayer(player_uuid, 16, 9_200, start.Add(3*time.Hour).Add(5*time.Minute))
			players[1] = newPlayer(player_uuid, 17, 9_500, start.Add(3*time.Hour).Add(40*time.Minute))
			players[2] = newPlayer(player_uuid, 18, 9_900, start.Add(4*time.Hour).Add(05*time.Minute))
			players[3] = newPlayer(player_uuid, 20, 10_900, start.Add(4*time.Hour).Add(45*time.Minute))
			players[4] = newPlayer(player_uuid, 21, 11_900, start.Add(4*time.Hour).Add(55*time.Minute))
			players[5] = newPlayer(player_uuid, 22, 12_900, start.Add(5*time.Hour).Add(15*time.Minute))

			playerData := storeStats(t, p, players...)

			sessions, err := p.GetSessions(ctx, player_uuid, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []Session{
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
			p := newPostgresPersistor(t, db, "short_pauses")
			player_uuid := newUUID(t)
			start := time.Date(2025, time.December, 1, 7, 13, 34, 987_654_321, time.FixedZone("UTC", 3600*7))

			players := make([]*domain.PlayerPIT, 6)
			players[0] = newPlayer(player_uuid, 16, 9_200, start.Add(1*time.Hour).Add(5*time.Minute))
			players[1] = newPlayer(player_uuid, 16, 9_500, start.Add(1*time.Hour).Add(40*time.Minute))
			players[2] = newPlayer(player_uuid, 16, 9_600, start.Add(2*time.Hour).Add(05*time.Minute))
			players[3] = newPlayer(player_uuid, 17, 10_900, start.Add(2*time.Hour).Add(45*time.Minute))
			players[4] = newPlayer(player_uuid, 17, 10_900, start.Add(2*time.Hour).Add(55*time.Minute))
			players[5] = newPlayer(player_uuid, 17, 11_900, start.Add(3*time.Hour).Add(15*time.Minute))

			playerData := storeStats(t, p, players...)

			sessions, err := p.GetSessions(ctx, player_uuid, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []Session{
				{
					Start:       *playerData[0],
					End:         *playerData[5],
					Consecutive: true,
				},
			}
			requireEqualSessions(t, expectedSessions, sessions)
		})
	})
}
