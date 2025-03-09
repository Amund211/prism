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
			require.NoError(t, err)

			storeStats(t, p, instructions...)

			txx, err = db.Beginx()
			require.NoError(t, err)
			defer txx.Rollback()

			_, err = txx.ExecContext(ctx, fmt.Sprintf("SET search_path TO %s", pq.QuoteIdentifier(p.schema)))
			require.NoError(t, err)

			var count int
			err = txx.QueryRowxContext(ctx, "SELECT COUNT(*) FROM stats").Scan(&count)
			require.NoError(t, err)
			require.Equal(t, len(instructions), count)

			err = txx.Commit()
			require.NoError(t, err)
		}

		requireDistribution := func(t *testing.T, history []PlayerDataPIT, expectedDistribution []time.Time) {
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

			require.Len(t, instructions, 24*4+1)

			setStoredStats(t, p, instructions...)

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

			instructions := make([]storageInstruction, 13)
			// Before start
			instructions[0] = storageInstruction{player_uuid, start.Add(0 * time.Hour).Add(-1 * time.Minute), newHypixelAPIPlayer(0)}

			// First 30 min interval
			instructions[1] = storageInstruction{player_uuid, start.Add(0 * time.Hour).Add(7 * time.Minute), newHypixelAPIPlayer(1)}
			instructions[2] = storageInstruction{player_uuid, start.Add(0 * time.Hour).Add(17 * time.Minute), newHypixelAPIPlayer(2)}

			// Second 30 min interval
			instructions[3] = storageInstruction{player_uuid, start.Add(0 * time.Hour).Add(37 * time.Minute), newHypixelAPIPlayer(3)}

			// Sixth 30 min interval
			instructions[4] = storageInstruction{player_uuid, start.Add(2 * time.Hour).Add(40 * time.Minute), newHypixelAPIPlayer(4)}
			instructions[5] = storageInstruction{player_uuid, start.Add(2 * time.Hour).Add(45 * time.Minute), newHypixelAPIPlayer(5)}
			instructions[6] = storageInstruction{player_uuid, start.Add(2 * time.Hour).Add(50 * time.Minute), newHypixelAPIPlayer(6)}
			instructions[7] = storageInstruction{player_uuid, start.Add(2 * time.Hour).Add(55 * time.Minute), newHypixelAPIPlayer(7)}

			// Seventh 30 min interval
			instructions[8] = storageInstruction{player_uuid, start.Add(3 * time.Hour).Add(1 * time.Minute), newHypixelAPIPlayer(8)}

			// Eighth 30 min interval
			instructions[9] = storageInstruction{player_uuid, start.Add(3 * time.Hour).Add(47 * time.Minute), newHypixelAPIPlayer(9)}
			instructions[10] = storageInstruction{player_uuid, start.Add(3 * time.Hour).Add(59 * time.Minute), newHypixelAPIPlayer(10)}

			// After end
			instructions[11] = storageInstruction{player_uuid, start.Add(4 * time.Hour).Add(1 * time.Minute), newHypixelAPIPlayer(11)}
			instructions[12] = storageInstruction{player_uuid, start.Add(4000 * time.Hour).Add(1 * time.Minute), newHypixelAPIPlayer(12)}

			setStoredStats(t, p, instructions...)

			// Get entries at the start and end of each 30 min interval (8 in total)
			history, err := p.GetHistory(ctx, player_uuid, start, start.Add(4*time.Hour), 16)
			require.NoError(t, err)

			expectedHistory := []storageInstruction{
				instructions[1],
				instructions[2],

				instructions[3],

				instructions[4],
				instructions[7],

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
							instructions := []storageInstruction{
								{player_uuid, queriedAt, newHypixelAPIPlayer(1)},
							}

							storeStats(t, p, instructions...)

							history, err := p.GetHistory(ctx, player_uuid, start, end, limit)
							require.NoError(t, err)

							require.Len(t, history, 1)

							expectedPIT := instructions[0]
							playerPIT := history[0]

							require.Equal(t, player_uuid, expectedPIT.uuid)
							require.Equal(t, player_uuid, playerPIT.UUID)

							// Mock data matches
							require.Equal(t, *expectedPIT.player.Stats.Bedwars.Kills, *playerPIT.Overall.Kills)

							require.WithinDuration(t, expectedPIT.queriedAt, playerPIT.QueriedAt, 0)
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
						instructions := []storageInstruction{
							{player_uuid, start.Add(time.Minute), newHypixelAPIPlayer(1)},
							{player_uuid, end.Add(-1 * time.Minute), newHypixelAPIPlayer(10)},
						}

						storeStats(t, p, instructions...)

						history, err := p.GetHistory(ctx, player_uuid, start, end, limit)
						require.NoError(t, err)

						require.Len(t, history, 2)

						for i, expectedPIT := range instructions {
							playerPIT := history[i]

							require.Equal(t, player_uuid, expectedPIT.uuid)
							require.Equal(t, player_uuid, playerPIT.UUID)

							// Mock data matches
							require.Equal(t, *expectedPIT.player.Stats.Bedwars.Kills, *playerPIT.Overall.Kills)

							require.WithinDuration(t, expectedPIT.queriedAt, playerPIT.QueriedAt, 0)
						}
					})
				}
			})
		})
	})

	t.Run("GetSessions", func(t *testing.T) {
		t.Parallel()
		type storageInstruction struct {
			uuid      string
			queriedAt time.Time
			player    *processing.HypixelAPIPlayer
		}

		storeStats := func(t *testing.T, p *PostgresStatsPersistor, instructions ...storageInstruction) []PlayerDataPIT {
			t.Helper()
			playerData := make([]PlayerDataPIT, len(instructions))
			for i, instruction := range instructions {
				// Add a random number to prevent de-duplication of the stored stats
				player := *instruction.player
				player.Stats.Bedwars.SoloWinstreak = &i
				err := p.StoreStats(ctx, instruction.uuid, &player, instruction.queriedAt)
				require.NoError(t, err)

				history, err := p.GetHistory(ctx, instruction.uuid, instruction.queriedAt, instruction.queriedAt.Add(1*time.Microsecond), 2)
				require.NoError(t, err)
				if len(history) == 0 {
					// NOTE: If stats are within a short interval with no changes, they won't get stored
					playerData[i] = PlayerDataPIT{ID: "NOT-STORED-ENTRY"}
					continue
				}
				require.Len(t, history, 1)
				playerData[i] = history[0]
			}
			return playerData
		}

		newPlayer := func(uuid string, gamesPlayed int, exp float64) *processing.HypixelAPIPlayer {
			return &processing.HypixelAPIPlayer{
				Stats: &processing.HypixelAPIStats{
					Bedwars: &processing.HypixelAPIBedwarsStats{
						Experience:  &exp,
						GamesPlayed: &gamesPlayed,
					},
				},
			}
		}

		requireEqualSessions := func(t *testing.T, expected, actual []Session) {
			t.Helper()

			type normalizedPlayerDataPIT struct {
				id                string
				queriedAtISO      string
				dataFormatVersion int
				uuid              string
				experience        float64
				gamesPlayed       int
				soloWinstreak     int
			}

			type normalizedSession struct {
				start normalizedPlayerDataPIT
				end   normalizedPlayerDataPIT
			}

			normalizePlayerData := func(playerData PlayerDataPIT) normalizedPlayerDataPIT {
				exp := -1.0
				if playerData.Experience != nil {
					exp = *playerData.Experience
				}
				gamesPlayed := -1
				if playerData.Overall.GamesPlayed != nil {
					gamesPlayed = *playerData.Overall.GamesPlayed
				}
				soloWinstreak := -1
				if playerData.Solo.Winstreak != nil {
					soloWinstreak = *playerData.Solo.Winstreak
				}
				return normalizedPlayerDataPIT{
					id:                playerData.ID,
					queriedAtISO:      playerData.QueriedAt.Format(time.RFC3339),
					dataFormatVersion: playerData.DataFormatVersion,
					uuid:              playerData.UUID,
					experience:        exp,
					gamesPlayed:       gamesPlayed,
					soloWinstreak:     soloWinstreak,
				}

			}

			expectedNormalized := make([]normalizedSession, len(expected))
			for i, session := range expected {
				expectedNormalized[i] = normalizedSession{
					start: normalizePlayerData(session.Start),
					end:   normalizePlayerData(session.End),
				}
			}

			actualNormalized := make([]normalizedSession, len(actual))
			for i, session := range actual {
				actualNormalized[i] = normalizedSession{
					start: normalizePlayerData(session.Start),
					end:   normalizePlayerData(session.End),
				}
			}
			require.Equal(t, expectedNormalized, actualNormalized)
		}

		t.Run("random clusters", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPersistor(t, db, "get_sessions_random_clusters")
			player_uuid := newUUID(t)
			start := time.Date(2022, time.February, 14, 0, 0, 0, 0, time.FixedZone("UTC", 3600*1))

			instructions := make([]storageInstruction, 26)
			// Ended session befor the start
			instructions[0] = storageInstruction{player_uuid, start.Add(-8 * time.Hour).Add(-1 * time.Minute), newPlayer(player_uuid, 10, 1_000)}
			instructions[1] = storageInstruction{player_uuid, start.Add(-8 * time.Hour).Add(7 * time.Minute), newPlayer(player_uuid, 11, 1_300)}
			instructions[2] = storageInstruction{player_uuid, start.Add(-8 * time.Hour).Add(17 * time.Minute), newPlayer(player_uuid, 12, 1_600)}

			// Session starting just before the start
			// Some inactivity at the start of the session
			instructions[3] = storageInstruction{player_uuid, start.Add(0 * time.Hour).Add(-37 * time.Minute), newPlayer(player_uuid, 12, 1_600)}
			instructions[4] = storageInstruction{player_uuid, start.Add(0 * time.Hour).Add(-27 * time.Minute), newPlayer(player_uuid, 12, 1_600)}
			instructions[5] = storageInstruction{player_uuid, start.Add(0 * time.Hour).Add(-17 * time.Minute), newPlayer(player_uuid, 12, 1_600)}
			instructions[6] = storageInstruction{player_uuid, start.Add(0 * time.Hour).Add(-12 * time.Minute), newPlayer(player_uuid, 13, 1_900)}
			instructions[7] = storageInstruction{player_uuid, start.Add(0 * time.Hour).Add(2 * time.Minute), newPlayer(player_uuid, 14, 2_200)}
			// One hour space between entries
			instructions[8] = storageInstruction{player_uuid, start.Add(0 * time.Hour).Add(38 * time.Minute), newPlayer(player_uuid, 15, 7_200)}
			instructions[9] = storageInstruction{player_uuid, start.Add(1 * time.Hour).Add(38 * time.Minute), newPlayer(player_uuid, 16, 7_900)}
			// One hour space between stat change, with some inactivity events in between
			instructions[10] = storageInstruction{player_uuid, start.Add(1 * time.Hour).Add(45 * time.Minute), newPlayer(player_uuid, 17, 8_900)}
			instructions[11] = storageInstruction{player_uuid, start.Add(1 * time.Hour).Add(55 * time.Minute), newPlayer(player_uuid, 17, 8_900)}
			instructions[12] = storageInstruction{player_uuid, start.Add(2 * time.Hour).Add(5 * time.Minute), newPlayer(player_uuid, 17, 8_900)}
			instructions[13] = storageInstruction{player_uuid, start.Add(2 * time.Hour).Add(15 * time.Minute), newPlayer(player_uuid, 17, 8_900)}
			instructions[14] = storageInstruction{player_uuid, start.Add(2 * time.Hour).Add(25 * time.Minute), newPlayer(player_uuid, 17, 8_900)}
			instructions[15] = storageInstruction{player_uuid, start.Add(2 * time.Hour).Add(35 * time.Minute), newPlayer(player_uuid, 17, 8_900)}
			instructions[16] = storageInstruction{player_uuid, start.Add(2 * time.Hour).Add(45 * time.Minute), newPlayer(player_uuid, 18, 9_500)}
			// Some inactivity at the end
			instructions[17] = storageInstruction{player_uuid, start.Add(2 * time.Hour).Add(55 * time.Minute), newPlayer(player_uuid, 18, 9_500)}
			instructions[18] = storageInstruction{player_uuid, start.Add(3 * time.Hour).Add(5 * time.Minute), newPlayer(player_uuid, 18, 9_500)}
			instructions[19] = storageInstruction{player_uuid, start.Add(3 * time.Hour).Add(15 * time.Minute), newPlayer(player_uuid, 18, 9_500)}
			instructions[20] = storageInstruction{player_uuid, start.Add(3 * time.Hour).Add(25 * time.Minute), newPlayer(player_uuid, 18, 9_500)}
			instructions[21] = storageInstruction{player_uuid, start.Add(3 * time.Hour).Add(35 * time.Minute), newPlayer(player_uuid, 18, 9_500)}
			instructions[22] = storageInstruction{player_uuid, start.Add(3 * time.Hour).Add(45 * time.Minute), newPlayer(player_uuid, 18, 9_500)}
			instructions[23] = storageInstruction{player_uuid, start.Add(3 * time.Hour).Add(55 * time.Minute), newPlayer(player_uuid, 18, 9_500)}

			// New activity 71 minutues after the last entry -> new session
			instructions[24] = storageInstruction{player_uuid, start.Add(3 * time.Hour).Add(56 * time.Minute), newPlayer(player_uuid, 18, 9_500)}
			instructions[25] = storageInstruction{player_uuid, start.Add(4 * time.Hour).Add(16 * time.Minute), newPlayer(player_uuid, 19, 10_800)}

			playerData := storeStats(t, p, instructions...)

			sessions, err := p.GetSessions(ctx, player_uuid, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []Session{
				{
					Start: playerData[5],
					End:   playerData[16],
				},
				{
					Start: playerData[24],
					End:   playerData[25],
				},
			}
			requireEqualSessions(t, expectedSessions, sessions)
		})

		t.Run("Single stat", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPersistor(t, db, "get_sessions_single")
			player_uuid := newUUID(t)
			start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*8))

			instructions := make([]storageInstruction, 1)
			instructions[0] = storageInstruction{player_uuid, start.Add(6 * time.Hour).Add(7 * time.Minute), newPlayer(player_uuid, 11, 1_300)}

			_ = storeStats(t, p, instructions...)

			sessions, err := p.GetSessions(ctx, player_uuid, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			require.Len(t, sessions, 0)
		})

		t.Run("Single stat at the start", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPersistor(t, db, "get_sessions_single_at_start")
			player_uuid := newUUID(t)
			start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*8))

			instructions := make([]storageInstruction, 3)
			instructions[0] = storageInstruction{player_uuid, start.Add(6 * time.Hour).Add(7 * time.Minute), newPlayer(player_uuid, 9, 1_000)}

			instructions[1] = storageInstruction{player_uuid, start.Add(8 * time.Hour).Add(-1 * time.Minute), newPlayer(player_uuid, 10, 1_100)}
			instructions[2] = storageInstruction{player_uuid, start.Add(8 * time.Hour).Add(7 * time.Minute), newPlayer(player_uuid, 11, 1_300)}

			playerData := storeStats(t, p, instructions...)

			sessions, err := p.GetSessions(ctx, player_uuid, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []Session{
				{
					Start: playerData[1],
					End:   playerData[2],
				},
			}
			requireEqualSessions(t, expectedSessions, sessions)
		})

		t.Run("Single stat at the end", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPersistor(t, db, "get_sessions_single_at_end")
			player_uuid := newUUID(t)
			start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*8))

			instructions := make([]storageInstruction, 3)
			instructions[0] = storageInstruction{player_uuid, start.Add(6 * time.Hour).Add(-1 * time.Minute), newPlayer(player_uuid, 10, 1_000)}
			instructions[1] = storageInstruction{player_uuid, start.Add(6 * time.Hour).Add(7 * time.Minute), newPlayer(player_uuid, 11, 1_300)}

			instructions[2] = storageInstruction{player_uuid, start.Add(8 * time.Hour).Add(7 * time.Minute), newPlayer(player_uuid, 12, 1_600)}

			playerData := storeStats(t, p, instructions...)

			sessions, err := p.GetSessions(ctx, player_uuid, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []Session{
				{
					Start: playerData[0],
					End:   playerData[1],
				},
			}
			requireEqualSessions(t, expectedSessions, sessions)
		})

		t.Run("Single stat at start and end", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPersistor(t, db, "get_sessions_single_at_start_and_end")
			player_uuid := newUUID(t)
			start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*2))

			instructions := make([]storageInstruction, 4)
			instructions[0] = storageInstruction{player_uuid, start.Add(5 * time.Hour).Add(7 * time.Minute), newPlayer(player_uuid, 9, 1_000)}

			instructions[1] = storageInstruction{player_uuid, start.Add(8 * time.Hour).Add(-1 * time.Minute), newPlayer(player_uuid, 10, 1_000)}
			instructions[2] = storageInstruction{player_uuid, start.Add(8 * time.Hour).Add(7 * time.Minute), newPlayer(player_uuid, 11, 1_300)}

			instructions[3] = storageInstruction{player_uuid, start.Add(10 * time.Hour).Add(7 * time.Minute), newPlayer(player_uuid, 12, 1_600)}

			playerData := storeStats(t, p, instructions...)

			sessions, err := p.GetSessions(ctx, player_uuid, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []Session{
				{
					Start: playerData[1],
					End:   playerData[2],
				},
			}
			requireEqualSessions(t, expectedSessions, sessions)
		})

		t.Run("No stats", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPersistor(t, db, "get_sessions_no_stats")
			player_uuid := newUUID(t)
			start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*10))

			instructions := make([]storageInstruction, 0)

			_ = storeStats(t, p, instructions...)

			sessions, err := p.GetSessions(ctx, player_uuid, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			require.Len(t, sessions, 0)
		})

		t.Run("inactivity between sessions", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPersistor(t, db, "get_sessions_inactivity_between_sessions")
			player_uuid := newUUID(t)
			start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*2))

			instructions := make([]storageInstruction, 13)
			instructions[0] = storageInstruction{player_uuid, start.Add(2 * time.Hour).Add(30 * time.Minute), newPlayer(player_uuid, 16, 9_200)}
			instructions[1] = storageInstruction{player_uuid, start.Add(2 * time.Hour).Add(35 * time.Minute), newPlayer(player_uuid, 16, 9_200)}
			instructions[2] = storageInstruction{player_uuid, start.Add(2 * time.Hour).Add(45 * time.Minute), newPlayer(player_uuid, 17, 9_400)}
			instructions[3] = storageInstruction{player_uuid, start.Add(2 * time.Hour).Add(55 * time.Minute), newPlayer(player_uuid, 18, 9_500)}
			instructions[4] = storageInstruction{player_uuid, start.Add(3 * time.Hour).Add(5 * time.Minute), newPlayer(player_uuid, 18, 9_500)}
			instructions[5] = storageInstruction{player_uuid, start.Add(3 * time.Hour).Add(15 * time.Minute), newPlayer(player_uuid, 18, 9_500)}
			instructions[6] = storageInstruction{player_uuid, start.Add(3 * time.Hour).Add(25 * time.Minute), newPlayer(player_uuid, 18, 9_500)}
			instructions[7] = storageInstruction{player_uuid, start.Add(3 * time.Hour).Add(35 * time.Minute), newPlayer(player_uuid, 18, 9_500)}
			instructions[8] = storageInstruction{player_uuid, start.Add(3 * time.Hour).Add(45 * time.Minute), newPlayer(player_uuid, 18, 9_500)}
			instructions[9] = storageInstruction{player_uuid, start.Add(3 * time.Hour).Add(55 * time.Minute), newPlayer(player_uuid, 18, 9_500)}
			instructions[10] = storageInstruction{player_uuid, start.Add(3 * time.Hour).Add(56 * time.Minute), newPlayer(player_uuid, 18, 9_500)}
			instructions[11] = storageInstruction{player_uuid, start.Add(4 * time.Hour).Add(16 * time.Minute), newPlayer(player_uuid, 19, 10_800)}
			instructions[12] = storageInstruction{player_uuid, start.Add(4 * time.Hour).Add(20 * time.Minute), newPlayer(player_uuid, 19, 10_800)}

			playerData := storeStats(t, p, instructions...)

			sessions, err := p.GetSessions(ctx, player_uuid, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []Session{
				{
					Start: playerData[1],
					End:   playerData[3],
				},
				{
					Start: playerData[10],
					End:   playerData[11],
				},
			}
			requireEqualSessions(t, expectedSessions, sessions)
		})

		t.Run("1 hr inactivity between sessions", func(t *testing.T) {
			t.Parallel()
			p := newPostgresPersistor(t, db, "get_sessions_1_hr_inactivity_between_sessions")
			player_uuid := newUUID(t)
			start := time.Date(2021, time.January, 1, 0, 0, 0, 0, time.FixedZone("UTC", -3600*2))

			instructions := make([]storageInstruction, 4)
			// Session 1
			instructions[0] = storageInstruction{player_uuid, start.Add(1 * time.Hour).Add(5 * time.Minute), newPlayer(player_uuid, 16, 9_200)}
			instructions[1] = storageInstruction{player_uuid, start.Add(1 * time.Hour).Add(30 * time.Minute), newPlayer(player_uuid, 17, 9_400)}
			// Session 2
			instructions[2] = storageInstruction{player_uuid, start.Add(1 * time.Hour).Add(45 * time.Minute), newPlayer(player_uuid, 17, 9_400)}
			instructions[3] = storageInstruction{player_uuid, start.Add(2 * time.Hour).Add(31 * time.Minute), newPlayer(player_uuid, 18, 10_800)}

			playerData := storeStats(t, p, instructions...)

			sessions, err := p.GetSessions(ctx, player_uuid, start, start.Add(24*time.Hour))
			require.NoError(t, err)

			expectedSessions := []Session{
				{
					Start: playerData[0],
					End:   playerData[1],
				},
				{
					Start: playerData[2],
					End:   playerData[3],
				},
			}
			requireEqualSessions(t, expectedSessions, sessions)
		})
	})
}
