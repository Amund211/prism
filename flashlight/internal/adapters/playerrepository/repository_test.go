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
	db, err := database.NewPostgresDatabase(database.LocalConnectionString)
	require.NoError(t, err)

	now := time.Now()

	t.Run("StorePlayer", func(t *testing.T) {
		t.Parallel()

		schemaName := "store_stats"
		p := newPostgresPlayerRepository(t, db, schemaName)

		requireStored := func(t *testing.T, player *domain.PlayerPIT, targetCount int) {
			t.Helper()

			normalizedUUID, err := strutils.NormalizeUUID(player.UUID)
			require.NoError(t, err)

			playerData, err := playerToDataStorage(player)
			require.NoError(t, err)

			txx, err := db.Beginx()
			require.NoError(t, err)
			defer txx.Rollback()

			_, err = txx.ExecContext(ctx, fmt.Sprintf("SET search_path TO %s", pq.QuoteIdentifier(schemaName)))
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
			player := domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(0).BuildPtr(now)

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

			player1 := domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(1).BuildPtr(t1)
			player2 := domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(2).BuildPtr(t2)

			requireNotStored(t, player1)
			err := p.StorePlayer(ctx, player1)
			require.NoError(t, err)
			requireStoredOnce(t, player1)

			requireNotStored(t, player2)
			err = p.StorePlayer(ctx, player2)
			require.NoError(t, err)
			requireStoredOnce(t, player2)

			// We never stored these combinations
			player1t2 := domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(1).BuildPtr(t2)
			requireNotStored(t, player1t2)
			player2t1 := domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(2).BuildPtr(t1)
			requireNotStored(t, player2t1)
		})

		t.Run("stats are stored within a short time span if they are different", func(t *testing.T) {
			t.Parallel()
			playerUUID := domaintest.NewUUID(t)
			t1 := now

			player1 := domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(1).BuildPtr(t1)

			requireNotStored(t, player1)
			err := p.StorePlayer(ctx, player1)
			require.NoError(t, err)
			requireStoredOnce(t, player1)

			t2 := t1.Add(time.Millisecond)
			player2 := domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(2).BuildPtr(t2)

			requireNotStored(t, player2)
			err = p.StorePlayer(ctx, player2)
			require.NoError(t, err)
			requireStoredOnce(t, player2)
		})

		t.Run("consecutive duplicate stats are not stored", func(t *testing.T) {
			t.Parallel()
			playerUUID := domaintest.NewUUID(t)

			t1 := now
			player1 := domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(1).BuildPtr(t1)

			requireNotStored(t, player1)
			err := p.StorePlayer(ctx, player1)
			require.NoError(t, err)
			requireStoredOnce(t, player1)

			for i := 1; i < 60; i++ {
				t2 := t1.Add(time.Duration(i) * time.Minute)
				player2 := domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(1).BuildPtr(t2)
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
			player1 := domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(1).BuildPtr(t1)

			requireNotStored(t, player1)
			err := p.StorePlayer(ctx, player1)
			require.NoError(t, err)
			requireStoredOnce(t, player1)

			// Consecutive duplicate data is more than an hour old -> store this one
			t2 := t1.Add(1 * time.Hour)
			player2 := domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(1).BuildPtr(t2)

			err = p.StorePlayer(ctx, player2)
			require.NoError(t, err)
			requireStoredOnce(t, player2)
		})

		t.Run("non-consecutive duplicate stats are stored", func(t *testing.T) {
			t.Parallel()
			playerUUID := domaintest.NewUUID(t)

			t1 := now
			player1 := domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(1).BuildPtr(t1)

			requireNotStored(t, player1)
			err := p.StorePlayer(ctx, player1)
			require.NoError(t, err)
			requireStoredOnce(t, player1)

			t2 := t1.Add(2 * time.Minute)
			player2 := domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(2).BuildPtr(t2)

			requireNotStored(t, player2)
			err = p.StorePlayer(ctx, player2)
			require.NoError(t, err)
			requireStoredOnce(t, player2)

			// Old duplicate data is not consecutive any more -> store it
			t3 := t2.Add(2 * time.Minute)
			player3 := domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(1).BuildPtr(t3)
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

			_, err = txx.ExecContext(ctx, fmt.Sprintf("SET search_path TO %s", pq.QuoteIdentifier(schemaName)))
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
			player2 := domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(1).BuildPtr(t2)
			err = p.StorePlayer(ctx, player2)
			require.NoError(t, err)
			requireStoredOnce(t, player2)
		})

		t.Run("same data for multiple users", func(t *testing.T) {
			t.Parallel()
			t1 := now
			uuid1 := domaintest.NewUUID(t)
			uuid2 := domaintest.NewUUID(t)
			player1 := domaintest.NewPlayerBuilder(uuid1).Fours().WithGamesPlayed(3).BuildPtr(t1)
			player2 := domaintest.NewPlayerBuilder(uuid2).Fours().WithGamesPlayed(3).BuildPtr(t1)

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
					player := domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(i).BuildPtr(t1)

					err := p.StorePlayer(ctx, player)
					require.NoError(t, err)
					requireStoredOnce(t, player)
				}
			})
			t.Run("when storing for the same player at the same time", func(t *testing.T) {
				t.Parallel()
				playerUUID := domaintest.NewUUID(t)
				t1 := now
				player := domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(1).BuildPtr(t1)

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
			player := domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(11).BuildPtr(now)

			requireNotStored(t, player)
			err := p.StorePlayer(ctx, player)
			require.NoError(t, err)
			requireStoredOnce(t, player)

			txx, err := db.Beginx()
			require.NoError(t, err)
			defer txx.Rollback()

			_, err = txx.ExecContext(ctx, fmt.Sprintf("SET search_path TO %s", pq.QuoteIdentifier(schemaName)))
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
			player := domaintest.NewPlayerBuilder(playerUUID).WithDBID(&dbID).BuildPtr(now)

			err = p.StorePlayer(ctx, player)
			require.Error(t, err)
			require.Contains(t, err.Error(), "already has a DBID")
		})
	})

	t.Run("GetPlayerPITs", func(t *testing.T) {
		t.Parallel()
		p := newPostgresPlayerRepository(t, db, "get_player_pits_tests")

		now := time.Now().Truncate(time.Millisecond)

		storePlayers := func(t *testing.T, p PlayerRepository, players ...*domain.PlayerPIT) {
			t.Helper()
			for _, player := range players {
				err := p.StorePlayer(ctx, player)
				require.NoError(t, err)
			}
		}

		t.Run("fetches stored players within given interval", func(t *testing.T) {
			t.Parallel()

			playerUUID := domaintest.NewUUID(t)

			p1 := domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(1).BuildPtr(now.Add(-2 * time.Hour))
			p2 := domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(2).BuildPtr(now)
			p3 := domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(3).BuildPtr(now.Add(2 * time.Minute))
			p4 := domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(4).BuildPtr(now.Add(2 * time.Hour))

			storePlayers(t, p, p1, p2, p3, p4)

			players, err := p.GetPlayerPITs(ctx, playerUUID, now, now.Add(1*time.Hour))
			require.NoError(t, err)

			require.Len(t, players, 2)
			r1 := players[0]
			require.Equal(t, p2.UUID, r1.UUID)
			require.WithinDuration(t, p2.QueriedAt, r1.QueriedAt, 0)
			requireValidDBID(t, r1.DBID)

			r2 := players[1]
			require.Equal(t, p3.UUID, r2.UUID)
			require.WithinDuration(t, p3.QueriedAt, r2.QueriedAt, 0)
			requireValidDBID(t, r2.DBID)
		})

		t.Run("fetches all player data", func(t *testing.T) {
			t.Parallel()

			playerUUID := domaintest.NewUUID(t)

			timePtr := func(timeStr string) *time.Time {
				t.Helper()
				timeTime, err := time.Parse(time.RFC3339, timeStr)
				require.NoError(t, err)
				return &timeTime
			}

			player := &domain.PlayerPIT{
				QueriedAt: now,

				UUID: playerUUID,

				Displayname: new("somename"),
				LastLogin:   timePtr("2023-01-01T00:00:00Z"),
				LastLogout:  timePtr("2023-01-02T00:00:00Z"),

				MissingBedwarsStats: false,

				Experience: 1_087_000,
				Solo: domain.GamemodeStatsPIT{
					Winstreak:   new(0),
					GamesPlayed: 1,
					Wins:        2,
					Losses:      3,
					BedsBroken:  3,
					BedsLost:    4,
					FinalKills:  6,
					FinalDeaths: 7,
					Kills:       8,
					Deaths:      9,
				},
				Doubles: domain.GamemodeStatsPIT{
					Winstreak:   new(100),
					GamesPlayed: 101,
					Wins:        102,
					Losses:      103,
					BedsBroken:  104,
					BedsLost:    105,
					FinalKills:  106,
					FinalDeaths: 107,
					Kills:       108,
					Deaths:      109,
				},
				Threes: domain.GamemodeStatsPIT{
					Winstreak:   nil,
					GamesPlayed: 201,
					Wins:        202,
					Losses:      203,
					BedsBroken:  204,
					BedsLost:    205,
					FinalKills:  206,
					FinalDeaths: 207,
					Kills:       208,
					Deaths:      209,
				},
				Fours: domain.GamemodeStatsPIT{
					Winstreak:   nil,
					GamesPlayed: 301,
					Wins:        302,
					Losses:      303,
					BedsBroken:  304,
					BedsLost:    305,
					FinalKills:  306,
					FinalDeaths: 307,
					Kills:       308,
					Deaths:      309,
				},
				Overall: domain.GamemodeStatsPIT{
					Winstreak:   nil,
					GamesPlayed: 401,
					Wins:        402,
					Losses:      403,
					BedsBroken:  404,
					BedsLost:    405,
					FinalKills:  406,
					FinalDeaths: 407,
					Kills:       408,
					Deaths:      409,
				},
			}

			storePlayers(t, p, player)

			players, err := p.GetPlayerPITs(ctx, playerUUID, now, now.Add(1*time.Hour))
			require.NoError(t, err)

			require.Len(t, players, 1)
			result := players[0]
			require.Equal(t, player.UUID, result.UUID)
			require.WithinDuration(t, player.QueriedAt, result.QueriedAt, 0)
			requireValidDBID(t, result.DBID)
			require.Equal(t, player.Experience, result.Experience)
			domaintest.RequireEqualStats(t, player.Solo, result.Solo)
			domaintest.RequireEqualStats(t, player.Doubles, result.Doubles)
			domaintest.RequireEqualStats(t, player.Threes, result.Threes)
			domaintest.RequireEqualStats(t, player.Fours, result.Fours)
			domaintest.RequireEqualStats(t, player.Overall, result.Overall)

			// Not stored to postgres
			require.Empty(t, result.Displayname)
			require.Empty(t, result.LastLogin)
			require.Empty(t, result.LastLogout)
		})

		t.Run("fetches unlimited players", func(t *testing.T) {
			t.Parallel()
			count := 1_000

			playerUUID := domaintest.NewUUID(t)

			toStore := make([]*domain.PlayerPIT, count)
			for i := range count {
				toStore[i] = domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(i).BuildPtr(now.Add(time.Duration(i) * time.Minute))
			}

			storePlayers(t, p, toStore...)

			players, err := p.GetPlayerPITs(ctx, playerUUID, now, now.Add(time.Duration(count-1)*time.Minute))
			require.NoError(t, err)

			require.Len(t, players, count)

			for i := range count {
				require.Equal(t, toStore[i].UUID, players[i].UUID)
				require.Equal(t, toStore[i].Overall.GamesPlayed, players[i].Overall.GamesPlayed)
				require.WithinDuration(t, toStore[i].QueriedAt, players[i].QueriedAt, 0)
				requireValidDBID(t, players[i].DBID)
			}
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
					domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(i).BuildPtr(janFirst21.Add(time.Duration(i)*interval)),
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
			players[0] = domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(0).BuildPtr(start.Add(0 * time.Hour).Add(-1 * time.Minute))

			// First 30 min interval
			players[1] = domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(1).BuildPtr(start.Add(0 * time.Hour).Add(7 * time.Minute))
			players[2] = domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(2).BuildPtr(start.Add(0 * time.Hour).Add(17 * time.Minute))

			// Second 30 min interval
			players[3] = domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(3).BuildPtr(start.Add(0 * time.Hour).Add(37 * time.Minute))

			// Sixth 30 min interval
			players[4] = domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(4).BuildPtr(start.Add(2 * time.Hour).Add(40 * time.Minute))
			players[5] = domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(5).BuildPtr(start.Add(2 * time.Hour).Add(45 * time.Minute))
			players[6] = domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(6).BuildPtr(start.Add(2 * time.Hour).Add(50 * time.Minute))
			players[7] = domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(7).BuildPtr(start.Add(2 * time.Hour).Add(55 * time.Minute))

			// Seventh 30 min interval
			players[8] = domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(8).BuildPtr(start.Add(3 * time.Hour).Add(1 * time.Minute))

			// Eighth 30 min interval
			players[9] = domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(9).BuildPtr(start.Add(3 * time.Hour).Add(47 * time.Minute))
			players[10] = domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(0).BuildPtr(start.Add(3 * time.Hour).Add(59 * time.Minute))

			// After end
			players[11] = domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(1).BuildPtr(start.Add(4 * time.Hour).Add(1 * time.Minute))
			players[12] = domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(2).BuildPtr(start.Add(4000 * time.Hour).Add(1 * time.Minute))

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
								domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(1).BuildPtr(queriedAt),
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
							domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(1).BuildPtr(start.Add(time.Minute)),
							domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(0).BuildPtr(end.Add(-1 * time.Minute)),
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
					domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(1).BuildPtr(start.Add(time.Minute)),
					domaintest.NewPlayerBuilder(playerUUID).Fours().WithGamesPlayed(0).BuildPtr(end.Add(-1 * time.Minute)),
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
						domaintest.NewPlayerBuilder(playerUUID).WithExperience(500).BuildPtr(time.Date(2021, time.January, 1, 12, 0, 0, 0, time.UTC)),
						domaintest.NewPlayerBuilder(playerUUID).WithExperience(1000).BuildPtr(time.Date(2021, time.January, 2, 12, 0, 0, 0, time.UTC)),
						domaintest.NewPlayerBuilder(playerUUID).WithExperience(1500).BuildPtr(time.Date(2021, time.January, 3, 12, 0, 0, 0, time.UTC)),
					},
					milestones: []int64{1200},
					expected: []domain.MilestoneAchievement{
						{
							Milestone: 1200,
							After: &domain.MilestoneAchievementStats{
								Player: domaintest.NewPlayerBuilder(playerUUID).WithExperience(1500).Build(time.Date(2021, time.January, 3, 12, 0, 0, 0, time.UTC)),
								Value:  1500,
							},
						},
					},
				},
				{
					name: "Multiple milestones reached",
					players: []*domain.PlayerPIT{
						domaintest.NewPlayerBuilder(playerUUID).WithExperience(500).BuildPtr(time.Date(2021, time.January, 1, 12, 0, 0, 0, time.UTC)),
						domaintest.NewPlayerBuilder(playerUUID).WithExperience(1000).BuildPtr(time.Date(2021, time.January, 2, 12, 0, 0, 0, time.UTC)),
						domaintest.NewPlayerBuilder(playerUUID).WithExperience(2000).BuildPtr(time.Date(2021, time.January, 3, 12, 0, 0, 0, time.UTC)),
						domaintest.NewPlayerBuilder(playerUUID).WithExperience(3000).BuildPtr(time.Date(2021, time.January, 4, 12, 0, 0, 0, time.UTC)),
					},
					milestones: []int64{800, 1500, 2500},
					expected: []domain.MilestoneAchievement{
						{
							Milestone: 800,
							After: &domain.MilestoneAchievementStats{
								Player: domaintest.NewPlayerBuilder(playerUUID).WithExperience(1000).Build(time.Date(2021, time.January, 2, 12, 0, 0, 0, time.UTC)),
								Value:  1000,
							},
						},
						{
							Milestone: 1500,
							After: &domain.MilestoneAchievementStats{
								Player: domaintest.NewPlayerBuilder(playerUUID).WithExperience(2000).Build(time.Date(2021, time.January, 3, 12, 0, 0, 0, time.UTC)),
								Value:  2000,
							},
						},
						{
							Milestone: 2500,
							After: &domain.MilestoneAchievementStats{
								Player: domaintest.NewPlayerBuilder(playerUUID).WithExperience(3000).Build(time.Date(2021, time.January, 4, 12, 0, 0, 0, time.UTC)),
								Value:  3000,
							},
						},
					},
				},
				{
					name: "No milestones reached",
					players: []*domain.PlayerPIT{
						domaintest.NewPlayerBuilder(playerUUID).WithExperience(500).BuildPtr(time.Date(2021, time.January, 1, 12, 0, 0, 0, time.UTC)),
						domaintest.NewPlayerBuilder(playerUUID).WithExperience(600).BuildPtr(time.Date(2021, time.January, 2, 12, 0, 0, 0, time.UTC)),
					},
					milestones: []int64{1000, 2000},
					expected:   []domain.MilestoneAchievement{},
				},
				{
					name: "Milestones skipped",
					players: []*domain.PlayerPIT{
						domaintest.NewPlayerBuilder(playerUUID).WithExperience(500).BuildPtr(time.Date(2021, time.January, 1, 12, 0, 0, 0, time.UTC)),
						domaintest.NewPlayerBuilder(playerUUID).WithExperience(10_000).BuildPtr(time.Date(2021, time.January, 2, 12, 0, 0, 0, time.UTC)),
						domaintest.NewPlayerBuilder(playerUUID).WithExperience(11_000).BuildPtr(time.Date(2021, time.January, 3, 12, 0, 0, 0, time.UTC)),
					},
					milestones: []int64{1_000, 5_000, 8_000, 12_000},
					expected: []domain.MilestoneAchievement{
						{
							Milestone: 8_000,
							After: &domain.MilestoneAchievementStats{
								Player: domaintest.NewPlayerBuilder(playerUUID).WithExperience(10_000).Build(time.Date(2021, time.January, 2, 12, 0, 0, 0, time.UTC)),
								Value:  10_000,
							},
						},
					},
				},
				{
					name: "Milestones skipped - final reached",
					players: []*domain.PlayerPIT{
						domaintest.NewPlayerBuilder(playerUUID).WithExperience(500).BuildPtr(time.Date(2021, time.January, 1, 12, 0, 0, 0, time.UTC)),
						domaintest.NewPlayerBuilder(playerUUID).WithExperience(100_000).BuildPtr(time.Date(2021, time.January, 2, 12, 0, 0, 0, time.UTC)),
						domaintest.NewPlayerBuilder(playerUUID).WithExperience(200_000).BuildPtr(time.Date(2021, time.January, 3, 12, 0, 0, 0, time.UTC)),
					},
					milestones: []int64{1_000, 5_000, 8_000, 12_000},
					expected: []domain.MilestoneAchievement{
						{
							Milestone: 12_000,
							After: &domain.MilestoneAchievementStats{
								Player: domaintest.NewPlayerBuilder(playerUUID).WithExperience(100_000).Build(time.Date(2021, time.January, 2, 12, 0, 0, 0, time.UTC)),
								Value:  100_000,
							},
						},
					},
				},
				{
					name: "Multiple sets of milestones skipped",
					players: []*domain.PlayerPIT{
						domaintest.NewPlayerBuilder(playerUUID).WithExperience(1_000).BuildPtr(time.Date(2025, time.March, 1, 19, 0, 0, 0, time.UTC)),
						domaintest.NewPlayerBuilder(playerUUID).WithExperience(6_001).BuildPtr(time.Date(2025, time.March, 2, 19, 0, 0, 0, time.UTC)),
					},
					milestones: []int64{500, 600, 700, 800, 900, 1_000, 2_000, 3_000, 4_000, 5_000, 6_000, 7_000, 8_000, 9_000, 10_000},
					expected: []domain.MilestoneAchievement{
						{
							Milestone: 1_000,
							After: &domain.MilestoneAchievementStats{
								Player: domaintest.NewPlayerBuilder(playerUUID).WithExperience(1_000).Build(time.Date(2025, time.March, 1, 19, 0, 0, 0, time.UTC)),
								Value:  1_000,
							},
						},
						{
							Milestone: 6_000,
							After: &domain.MilestoneAchievementStats{
								Player: domaintest.NewPlayerBuilder(playerUUID).WithExperience(6_001).Build(time.Date(2025, time.March, 2, 19, 0, 0, 0, time.UTC)),
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
