package accountrepository

import (
	"fmt"
	"log/slog"
	"os"
	"sync"
	"testing"
	"time"

	"github.com/jmoiron/sqlx"
	"github.com/lib/pq"
	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/adapters/database"
	"github.com/Amund211/flashlight/internal/domain"
)

func newPostgres(t *testing.T, db *sqlx.DB, schemaSuffix string) *Postgres {
	require.NotEmpty(t, schemaSuffix, "schemaSuffix must not be empty")
	schema := fmt.Sprintf("usernames_repo_test_%s", schemaSuffix)

	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))

	db.MustExec(fmt.Sprintf("DROP SCHEMA IF EXISTS %s CASCADE", pq.QuoteIdentifier(schema)))

	migrator := database.NewDatabaseMigrator(db, logger)

	err := migrator.Migrate(t.Context(), schema)
	require.NoError(t, err)

	return NewPostgres(db, schema)
}

func makeUUID(x int) string {
	if x < 0 || x > 9999 {
		panic("x must be between 0 and 9999")
	}
	return fmt.Sprintf("00000000-0000-0000-0000-%012x", x)
}

func TestPostgres(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping db tests in short mode.")
	}

	ctx := t.Context()
	db, err := database.NewPostgresDatabase(database.LOCAL_CONNECTION_STRING)
	require.NoError(t, err)

	now := time.Now()

	t.Run("Store/RemoveUsername", func(t *testing.T) {
		t.Parallel()

		getStoredUsernames := func(t *testing.T, p *Postgres) []dbUsernamesEntry {
			t.Helper()

			txx, err := db.Beginx()
			require.NoError(t, err)
			defer txx.Rollback()

			_, err = txx.ExecContext(ctx, fmt.Sprintf("SET search_path TO %s", pq.QuoteIdentifier(p.schema)))
			require.NoError(t, err)

			var entries []dbUsernamesEntry
			err = txx.SelectContext(ctx, &entries, "SELECT player_uuid, username, queried_at FROM usernames")
			require.NoError(t, err)

			return entries
		}

		expectStoredUsernames := func(t *testing.T, p *Postgres, expected ...dbUsernamesEntry) {
			t.Helper()

			type username struct {
				PlayerUUID string
				Username   string
				QueriedAt  string
			}

			convert := func(entries []dbUsernamesEntry) []username {
				converted := make([]username, len(entries))
				for i, entry := range entries {
					converted[i] = username{
						PlayerUUID: entry.PlayerUUID,
						Username:   entry.Username,
						QueriedAt:  entry.QueriedAt.Format(time.RFC3339),
					}
				}
				return converted
			}

			require.ElementsMatch(t, convert(expected), convert(getStoredUsernames(t, p)))
		}

		getStoredUsernameQueries := func(t *testing.T, p *Postgres) []dbUsernameQueriesEntry {
			t.Helper()

			txx, err := db.Beginx()
			require.NoError(t, err)
			defer txx.Rollback()

			_, err = txx.ExecContext(ctx, fmt.Sprintf("SET search_path TO %s", pq.QuoteIdentifier(p.schema)))
			require.NoError(t, err)

			var entries []dbUsernameQueriesEntry
			err = txx.SelectContext(ctx, &entries, "SELECT player_uuid, username, last_queried_at FROM username_queries")
			require.NoError(t, err)

			return entries
		}

		expectStoredUsernameQueries := func(t *testing.T, p *Postgres, expected ...dbUsernameQueriesEntry) {
			t.Helper()

			type usernameQuery struct {
				PlayerUUID    string
				Username      string
				LastQueriedAt string
			}

			convert := func(entries []dbUsernameQueriesEntry) []usernameQuery {
				converted := make([]usernameQuery, len(entries))
				for i, entry := range entries {
					converted[i] = usernameQuery{
						PlayerUUID:    entry.PlayerUUID,
						Username:      entry.Username,
						LastQueriedAt: entry.LastQueriedAt.Format(time.RFC3339),
					}
				}
				return converted
			}

			require.ElementsMatch(t, convert(expected), convert(getStoredUsernameQueries(t, p)))
		}

		t.Run("store single username", func(t *testing.T) {
			t.Parallel()

			p := newPostgres(t, db, "store_single_username")

			err := p.StoreAccount(ctx, domain.Account{
				UUID:      makeUUID(1),
				Username:  "testuser1",
				QueriedAt: now,
			})
			require.NoError(t, err)

			expectStoredUsernames(t, p, dbUsernamesEntry{
				PlayerUUID: makeUUID(1),
				Username:   "testuser1",
				QueriedAt:  now,
			},
			)

			expectStoredUsernameQueries(t, p, dbUsernameQueriesEntry{
				PlayerUUID:    makeUUID(1),
				Username:      "testuser1",
				LastQueriedAt: now,
			},
			)
		})

		t.Run("store multiple usernames for different players", func(t *testing.T) {
			t.Parallel()

			p := newPostgres(t, db, "store_multiple_usernames_different_players")

			t1 := now.Add(1 * time.Minute)
			err := p.StoreAccount(ctx, domain.Account{
				UUID:      makeUUID(1),
				Username:  "testuser1",
				QueriedAt: t1,
			})
			require.NoError(t, err)

			t2 := now.Add(2 * time.Minute)
			err = p.StoreAccount(ctx, domain.Account{
				UUID:      makeUUID(2),
				Username:  "testuser2",
				QueriedAt: t2,
			})
			require.NoError(t, err)

			expectStoredUsernames(t, p,
				dbUsernamesEntry{
					PlayerUUID: makeUUID(1),
					Username:   "testuser1",
					QueriedAt:  t1,
				},
				dbUsernamesEntry{
					PlayerUUID: makeUUID(2),
					Username:   "testuser2",
					QueriedAt:  t2,
				},
			)

			expectStoredUsernameQueries(t, p,
				dbUsernameQueriesEntry{
					PlayerUUID:    makeUUID(1),
					Username:      "testuser1",
					LastQueriedAt: t1,
				},
				dbUsernameQueriesEntry{
					PlayerUUID:    makeUUID(2),
					Username:      "testuser2",
					LastQueriedAt: t2,
				},
			)
		})

		t.Run("store duplicate uuid", func(t *testing.T) {
			t.Parallel()

			p := newPostgres(t, db, "store_duplicate_uuid")

			t1 := now.Add(1 * time.Minute)
			err := p.StoreAccount(ctx, domain.Account{
				UUID:      makeUUID(1),
				Username:  "testuser1",
				QueriedAt: t1,
			})
			require.NoError(t, err)

			expectStoredUsernames(t, p,
				dbUsernamesEntry{
					PlayerUUID: makeUUID(1),
					Username:   "testuser1",
					QueriedAt:  t1,
				},
			)
			expectStoredUsernameQueries(t, p,
				dbUsernameQueriesEntry{
					PlayerUUID:    makeUUID(1),
					Username:      "testuser1",
					LastQueriedAt: t1,
				},
			)

			t2 := now.Add(2 * time.Minute)
			err = p.StoreAccount(ctx, domain.Account{
				UUID:      makeUUID(1),
				Username:  "testuser2",
				QueriedAt: t2,
			})
			require.NoError(t, err)

			// Should replace existing entry with the given uuid to ensure no duplicates
			expectStoredUsernames(t, p,
				dbUsernamesEntry{
					PlayerUUID: makeUUID(1),
					Username:   "testuser2",
					QueriedAt:  t2,
				},
			)
			// Should store both the new and old username in the queries table
			expectStoredUsernameQueries(t, p,
				dbUsernameQueriesEntry{
					PlayerUUID:    makeUUID(1),
					Username:      "testuser1",
					LastQueriedAt: t1,
				},
				dbUsernameQueriesEntry{
					PlayerUUID:    makeUUID(1),
					Username:      "testuser2",
					LastQueriedAt: t2,
				},
			)
		})

		t.Run("store duplicate username", func(t *testing.T) {
			t.Parallel()

			p := newPostgres(t, db, "store_duplicate_username")

			t1 := now.Add(1 * time.Minute)
			err := p.StoreAccount(ctx, domain.Account{
				UUID:      makeUUID(1),
				Username:  "testuser1",
				QueriedAt: t1,
			})
			require.NoError(t, err)

			expectStoredUsernames(t, p,
				dbUsernamesEntry{
					PlayerUUID: makeUUID(1),
					Username:   "testuser1",
					QueriedAt:  t1,
				},
			)
			expectStoredUsernameQueries(t, p,
				dbUsernameQueriesEntry{
					PlayerUUID:    makeUUID(1),
					Username:      "testuser1",
					LastQueriedAt: t1,
				},
			)

			t2 := now.Add(2 * time.Minute)
			err = p.StoreAccount(ctx, domain.Account{
				UUID:      makeUUID(2),
				Username:  "testuser1",
				QueriedAt: t2,
			})
			require.NoError(t, err)

			// Should replace existing entry with the given username to ensure no duplicates
			expectStoredUsernames(t, p,
				dbUsernamesEntry{
					PlayerUUID: makeUUID(2),
					Username:   "testuser1",
					QueriedAt:  t2,
				},
			)
			// Should store both the new and old username in the queries table
			expectStoredUsernameQueries(t, p,
				dbUsernameQueriesEntry{
					PlayerUUID:    makeUUID(1),
					Username:      "testuser1",
					LastQueriedAt: t1,
				},
				dbUsernameQueriesEntry{
					PlayerUUID:    makeUUID(2),
					Username:      "testuser1",
					LastQueriedAt: t2,
				},
			)
		})

		t.Run("store duplicate username with different casing", func(t *testing.T) {
			t.Parallel()

			p := newPostgres(t, db, "store_duplicate_username_different_casing")

			t1 := now.Add(1 * time.Minute)
			err := p.StoreAccount(ctx, domain.Account{
				UUID:      makeUUID(1),
				Username:  "testuser1",
				QueriedAt: t1,
			})
			require.NoError(t, err)

			expectStoredUsernames(t, p,
				dbUsernamesEntry{
					PlayerUUID: makeUUID(1),
					Username:   "testuser1",
					QueriedAt:  t1,
				},
			)
			expectStoredUsernameQueries(t, p,
				dbUsernameQueriesEntry{
					PlayerUUID:    makeUUID(1),
					Username:      "testuser1",
					LastQueriedAt: t1,
				},
			)

			t2 := now.Add(2 * time.Minute)
			err = p.StoreAccount(ctx, domain.Account{
				UUID:      makeUUID(2),
				Username:  "TESTUSER1",
				QueriedAt: t2,
			})
			require.NoError(t, err)

			// Should replace existing entry with the given username to ensure no duplicates
			expectStoredUsernames(t, p,
				dbUsernamesEntry{
					PlayerUUID: makeUUID(2),
					Username:   "TESTUSER1",
					QueriedAt:  t2,
				},
			)
			// Should store both the new and old username in the queries table
			expectStoredUsernameQueries(t, p,
				dbUsernameQueriesEntry{
					PlayerUUID:    makeUUID(1),
					Username:      "testuser1",
					LastQueriedAt: t1,
				},
				dbUsernameQueriesEntry{
					PlayerUUID:    makeUUID(2),
					Username:      "TESTUSER1",
					LastQueriedAt: t2,
				},
			)
		})

		t.Run("store duplicate uuid and duplicate username", func(t *testing.T) {
			t.Parallel()

			// Store a uuid and username that both already exist in different rows
			p := newPostgres(t, db, "store_duplicate_uuid_and_duplicate_username")

			t1 := now.Add(1 * time.Minute)
			err := p.StoreAccount(ctx, domain.Account{
				UUID:      makeUUID(1),
				Username:  "testuser1",
				QueriedAt: t1,
			})
			require.NoError(t, err)

			err = p.StoreAccount(ctx, domain.Account{
				UUID:      makeUUID(2),
				Username:  "testuser2",
				QueriedAt: t1,
			})
			require.NoError(t, err)

			expectStoredUsernames(t, p,
				dbUsernamesEntry{
					PlayerUUID: makeUUID(1),
					Username:   "testuser1",
					QueriedAt:  t1,
				},
				dbUsernamesEntry{
					PlayerUUID: makeUUID(2),
					Username:   "testuser2",
					QueriedAt:  t1,
				},
			)
			expectStoredUsernameQueries(t, p,
				dbUsernameQueriesEntry{
					PlayerUUID:    makeUUID(1),
					Username:      "testuser1",
					LastQueriedAt: t1,
				},
				dbUsernameQueriesEntry{
					PlayerUUID:    makeUUID(2),
					Username:      "testuser2",
					LastQueriedAt: t1,
				},
			)

			t2 := now.Add(2 * time.Minute)
			err = p.StoreAccount(ctx, domain.Account{
				UUID:      makeUUID(1),
				Username:  "testuser2",
				QueriedAt: t2,
			})
			require.NoError(t, err)

			expectStoredUsernames(t, p,
				dbUsernamesEntry{
					PlayerUUID: makeUUID(1),
					Username:   "testuser2",
					QueriedAt:  t2,
				},
			)
			expectStoredUsernameQueries(t, p,
				dbUsernameQueriesEntry{
					PlayerUUID:    makeUUID(1),
					Username:      "testuser1",
					LastQueriedAt: t1,
				},
				dbUsernameQueriesEntry{
					PlayerUUID:    makeUUID(2),
					Username:      "testuser2",
					LastQueriedAt: t1,
				},
				dbUsernameQueriesEntry{
					PlayerUUID:    makeUUID(1),
					Username:      "testuser2",
					LastQueriedAt: t2,
				},
			)
		})

		t.Run("store identical uuid+username", func(t *testing.T) {
			t.Parallel()

			p := newPostgres(t, db, "store_identical_uuid_and_username")

			t1 := now.Add(1 * time.Minute)
			err := p.StoreAccount(ctx, domain.Account{
				UUID:      makeUUID(1),
				Username:  "testuser1",
				QueriedAt: t1,
			})
			require.NoError(t, err)

			expectStoredUsernames(t, p,
				dbUsernamesEntry{
					PlayerUUID: makeUUID(1),
					Username:   "testuser1",
					QueriedAt:  t1,
				},
			)
			expectStoredUsernameQueries(t, p,
				dbUsernameQueriesEntry{
					PlayerUUID:    makeUUID(1),
					Username:      "testuser1",
					LastQueriedAt: t1,
				},
			)

			t2 := now.Add(2 * time.Minute)
			err = p.StoreAccount(ctx, domain.Account{
				UUID:      makeUUID(1),
				Username:  "testuser1",
				QueriedAt: t2,
			})
			require.NoError(t, err)

			expectStoredUsernames(t, p,
				dbUsernamesEntry{
					PlayerUUID: makeUUID(1),
					Username:   "testuser1",
					QueriedAt:  t2,
				},
			)
			expectStoredUsernameQueries(t, p,
				dbUsernameQueriesEntry{
					PlayerUUID:    makeUUID(1),
					Username:      "testuser1",
					LastQueriedAt: t2,
				},
			)
		})

		t.Run("remove username", func(t *testing.T) {
			t.Parallel()

			p := newPostgres(t, db, "remove_username")

			err := p.StoreAccount(ctx, domain.Account{
				UUID:      makeUUID(1),
				Username:  "testuser1",
				QueriedAt: now,
			})
			require.NoError(t, err)

			expectStoredUsernames(t, p, dbUsernamesEntry{
				PlayerUUID: makeUUID(1),
				Username:   "testuser1",
				QueriedAt:  now,
			},
			)

			expectStoredUsernameQueries(t, p, dbUsernameQueriesEntry{
				PlayerUUID:    makeUUID(1),
				Username:      "testuser1",
				LastQueriedAt: now,
			},
			)

			err = p.RemoveUsername(ctx, "TestUser1")
			require.NoError(t, err)

			expectStoredUsernames(t, p)

			expectStoredUsernameQueries(t, p, dbUsernameQueriesEntry{
				PlayerUUID:    makeUUID(1),
				Username:      "testuser1",
				LastQueriedAt: now,
			},
			)

			err = p.RemoveUsername(ctx, "nonexistentuser")
			require.NoError(t, err)
		})

		t.Run("ensure no unique constraint violations", func(t *testing.T) {
			t.Parallel()
			limit := 20

			p := newPostgres(t, db, "ensure_no_unique_constraint_violations")

			wg := &sync.WaitGroup{}
			wg.Add(limit)

			for i := range limit {
				go func(i int) {
					defer wg.Done()
					t1 := now.Add(time.Duration(i) * time.Minute)
					err := p.StoreAccount(ctx, domain.Account{
						UUID:      makeUUID(333 + (i % 3)),
						Username:  fmt.Sprintf("testuser%d", i%2),
						QueriedAt: t1,
					})
					require.NoError(t, err)
				}(i)
			}

			wg.Wait()
		})

		t.Run("ensure no db connection leaks", func(t *testing.T) {
			t.Parallel()

			p := newPostgres(t, db, "ensure_no_db_connection_leaks")

			var maxConnections int
			err := db.QueryRowxContext(ctx, "show max_connections").Scan(&maxConnections)
			require.NoError(t, err)
			require.LessOrEqual(t, maxConnections, 1000, "max_connections should be less than 1000 to prevent tests from taking a long time")

			limit := maxConnections + 10

			t.Run("when storing for many different players", func(t *testing.T) {
				t.Parallel()
				for i := range limit {
					t1 := now.Add(time.Duration(i) * time.Minute)
					err := p.StoreAccount(ctx, domain.Account{
						UUID:      makeUUID(i),
						Username:  fmt.Sprintf("testuser%d", i),
						QueriedAt: t1,
					})
					require.NoError(t, err)
				}
			})
			t.Run("when storing for the same player at the same time", func(t *testing.T) {
				t.Parallel()
				for i := range limit {
					t1 := now.Add(time.Duration(i) * time.Minute)
					err := p.StoreAccount(ctx, domain.Account{
						UUID:      makeUUID(4_192),
						Username:  fmt.Sprintf("testuser%d", i),
						QueriedAt: t1,
					})
					require.NoError(t, err)
				}
			})
		})
	})

	t.Run("GetAccountByUsername", func(t *testing.T) {
		t.Parallel()
		p := newPostgres(t, db, "get_account_by_username")

		err := p.StoreAccount(ctx, domain.Account{
			UUID:      makeUUID(1),
			Username:  "Ghanima",
			QueriedAt: now.Add(-24 * time.Hour),
		})
		require.NoError(t, err)

		err = p.StoreAccount(ctx, domain.Account{
			UUID:      makeUUID(2),
			Username:  "Leto",
			QueriedAt: now,
		})
		require.NoError(t, err)

		err = p.StoreAccount(ctx, domain.Account{
			UUID:      makeUUID(3),
			Username:  "Siona",
			QueriedAt: now.Add(2 * time.Hour),
		})
		require.NoError(t, err)

		t.Run("get missing", func(t *testing.T) {
			t.Parallel()

			_, err := p.GetAccountByUsername(ctx, "nonexistentuser")
			require.ErrorIs(t, err, domain.ErrUsernameNotFound)
		})

		t.Run("get same casing", func(t *testing.T) {
			t.Parallel()

			account, err := p.GetAccountByUsername(ctx, "Leto")
			require.NoError(t, err)
			require.Equal(t, makeUUID(2), account.UUID)
			require.Equal(t, "Leto", account.Username)
			require.WithinDuration(t, now, account.QueriedAt, 1*time.Millisecond)
		})

		t.Run("get different casing", func(t *testing.T) {
			t.Parallel()

			account, err := p.GetAccountByUsername(ctx, "siona")
			require.NoError(t, err)
			require.Equal(t, makeUUID(3), account.UUID)
			require.Equal(t, "Siona", account.Username)
			require.WithinDuration(t, now.Add(2*time.Hour), account.QueriedAt, 1*time.Millisecond)
		})
	})

	t.Run("GetAccountByUUID", func(t *testing.T) {
		t.Parallel()
		p := newPostgres(t, db, "get_account_by_uuid")

		err := p.StoreAccount(ctx, domain.Account{
			UUID:      makeUUID(1),
			Username:  "Ghanima",
			QueriedAt: now.Add(24 * time.Hour),
		})
		require.NoError(t, err)

		err = p.StoreAccount(ctx, domain.Account{
			UUID:      makeUUID(2),
			Username:  "Leto",
			QueriedAt: now,
		})
		require.NoError(t, err)

		err = p.StoreAccount(ctx, domain.Account{
			UUID:      makeUUID(3),
			Username:  "Siona",
			QueriedAt: now.Add(-2 * time.Hour),
		})
		require.NoError(t, err)

		t.Run("get missing", func(t *testing.T) {
			t.Parallel()

			_, err := p.GetAccountByUUID(ctx, makeUUID(123))
			require.ErrorIs(t, err, domain.ErrUsernameNotFound)
		})

		t.Run("get same casing", func(t *testing.T) {
			t.Parallel()

			account, err := p.GetAccountByUUID(ctx, makeUUID(2))
			require.NoError(t, err)
			require.Equal(t, makeUUID(2), account.UUID)
			require.Equal(t, "Leto", account.Username)
			require.WithinDuration(t, now, account.QueriedAt, 1*time.Millisecond)
		})

		t.Run("get different casing", func(t *testing.T) {
			t.Parallel()

			account, err := p.GetAccountByUUID(ctx, makeUUID(3))
			require.NoError(t, err)
			require.Equal(t, makeUUID(3), account.UUID)
			require.Equal(t, "Siona", account.Username)
			require.WithinDuration(t, now.Add(-2*time.Hour), account.QueriedAt, 1*time.Millisecond)
		})
	})
}
