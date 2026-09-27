package credentialrepository

import (
	"bytes"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"testing"
	"time"

	"github.com/jmoiron/sqlx"
	"github.com/lib/pq"
	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/adapters/database"
	"github.com/Amund211/flashlight/internal/domain"
)

func newPostgres(t *testing.T, schemaSuffix string) (*Postgres, *sqlx.DB, string) {
	t.Helper()
	db, err := database.NewPostgresDatabase(database.LocalConnectionString)
	require.NoError(t, err)
	t.Cleanup(func() { _ = db.Close() })

	schema := fmt.Sprintf("credential_repo_test_%s", schemaSuffix)
	db.MustExec(fmt.Sprintf("DROP SCHEMA IF EXISTS %s CASCADE", pq.QuoteIdentifier(schema)))
	migrator := database.NewDatabaseMigrator(db, slog.New(slog.NewJSONHandler(os.Stdout, nil)))
	require.NoError(t, migrator.Migrate(t.Context(), schema))

	return NewPostgres(db, schema), db, schema
}

type storedCredential struct {
	CredentialHash []byte     `db:"credential_hash"`
	IdentityKey    string     `db:"identity_key"`
	ClientType     string     `db:"client_type"`
	CreatedAt      time.Time  `db:"created_at"`
	ExpiresAt      time.Time  `db:"expires_at"`
	LastUsedAt     *time.Time `db:"last_used_at"`
}

func readAll(t *testing.T, db *sqlx.DB, schema string) []storedCredential {
	t.Helper()
	var rows []storedCredential
	require.NoError(t, db.SelectContext(t.Context(), &rows, fmt.Sprintf(
		"SELECT credential_hash, identity_key, client_type, created_at, expires_at, last_used_at FROM %s.user_credentials ORDER BY identity_key",
		pq.QuoteIdentifier(schema))))
	return rows
}

var now = time.Date(2026, 9, 27, 12, 0, 0, 0, time.UTC)

func testCredential(hashByte byte, identityKey string) domain.UserCredential {
	return domain.UserCredential{
		Hash:        bytes.Repeat([]byte{hashByte}, 32),
		IdentityKey: identityKey,
		ClientType:  domain.MicrosoftClientRainbow,
		CreatedAt:   now,
		ExpiresAt:   now.Add(90 * 24 * time.Hour),
	}
}

func TestPostgresInsert(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping db tests in short mode.")
	}
	t.Parallel()

	t.Run("stores the row", func(t *testing.T) {
		t.Parallel()
		repo, db, schema := newPostgres(t, "stores")

		cred := testCredential(1, "a937646bf11544c38dbf9ae4a65669a0")
		require.NoError(t, repo.Insert(t.Context(), cred))

		rows := readAll(t, db, schema)
		require.Len(t, rows, 1)
		require.Equal(t, cred.Hash, rows[0].CredentialHash)
		require.Equal(t, cred.IdentityKey, rows[0].IdentityKey)
		require.Equal(t, "rainbow", rows[0].ClientType)
		require.True(t, cred.CreatedAt.Equal(rows[0].CreatedAt))
		require.True(t, cred.ExpiresAt.Equal(rows[0].ExpiresAt))
		require.Nil(t, rows[0].LastUsedAt)
	})

	t.Run("one identity holds many credentials", func(t *testing.T) {
		t.Parallel()
		repo, db, schema := newPostgres(t, "many")

		require.NoError(t, repo.Insert(t.Context(), testCredential(1, "a937646bf11544c38dbf9ae4a65669a0")))
		prism := testCredential(2, "a937646bf11544c38dbf9ae4a65669a0")
		prism.ClientType = domain.MicrosoftClientPrism
		require.NoError(t, repo.Insert(t.Context(), prism))

		require.Len(t, readAll(t, db, schema), 2)
	})

	t.Run("refuses a duplicate hash", func(t *testing.T) {
		t.Parallel()
		repo, _, _ := newPostgres(t, "duplicate")

		require.NoError(t, repo.Insert(t.Context(), testCredential(1, "a")))
		require.Error(t, repo.Insert(t.Context(), testCredential(1, "b")))
	})

	t.Run("refuses an incomplete credential", func(t *testing.T) {
		t.Parallel()
		repo, db, schema := newPostgres(t, "incomplete")

		for _, mutate := range []func(*domain.UserCredential){
			func(c *domain.UserCredential) { c.Hash = nil },
			func(c *domain.UserCredential) { c.Hash = []byte{1} },
			func(c *domain.UserCredential) { c.IdentityKey = "" },
			func(c *domain.UserCredential) { c.ClientType = "" },
			func(c *domain.UserCredential) { c.CreatedAt = time.Time{} },
			func(c *domain.UserCredential) { c.ExpiresAt = time.Time{} },
		} {
			cred := testCredential(3, "a")
			mutate(&cred)
			require.Error(t, repo.Insert(t.Context(), cred))
		}
		require.Empty(t, readAll(t, db, schema))
	})

	t.Run("indexes identity_key for logout", func(t *testing.T) {
		t.Parallel()
		_, db, schema := newPostgres(t, "index")

		var count int
		require.NoError(t, db.GetContext(t.Context(), &count,
			"SELECT count(*) FROM pg_indexes WHERE schemaname = $1 AND tablename = 'user_credentials' AND indexname = 'user_credentials_identity_key'",
			schema))
		require.Equal(t, 1, count)
	})
}

func hashOf(b byte) []byte {
	return bytes.Repeat([]byte{b}, 32)
}

func rowByHash(t *testing.T, db *sqlx.DB, schema string, hash []byte) storedCredential {
	t.Helper()
	for _, row := range readAll(t, db, schema) {
		if bytes.Equal(row.CredentialHash, hash) {
			return row
		}
	}
	t.Fatalf("no row for hash %x", hash[:1])
	return storedCredential{}
}

const (
	grace      = time.Minute
	idleWindow = 90 * 24 * time.Hour
)

func TestPostgresFind(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping db tests in short mode.")
	}
	t.Parallel()

	repo, _, _ := newPostgres(t, "find")
	live := testCredential(1, "a937646bf11544c38dbf9ae4a65669a0")
	live.ClientType = domain.MicrosoftClientPrism
	require.NoError(t, repo.Insert(t.Context(), live))
	expired := testCredential(2, "a937646bf11544c38dbf9ae4a65669a0")
	expired.ExpiresAt = now
	require.NoError(t, repo.Insert(t.Context(), expired))

	t.Run("a live credential", func(t *testing.T) {
		t.Parallel()
		got, err := repo.Find(t.Context(), live.Hash, now)
		require.NoError(t, err)
		require.Equal(t, live.Hash, got.Hash)
		require.Equal(t, live.IdentityKey, got.IdentityKey)
		require.Equal(t, domain.MicrosoftClientPrism, got.ClientType)
		require.True(t, live.CreatedAt.Equal(got.CreatedAt))
		require.True(t, live.ExpiresAt.Equal(got.ExpiresAt))
	})

	t.Run("an expired credential is stale", func(t *testing.T) {
		t.Parallel()
		_, err := repo.Find(t.Context(), expired.Hash, now)
		require.ErrorIs(t, err, domain.ErrUserCredentialStale)
	})

	t.Run("an unknown credential", func(t *testing.T) {
		t.Parallel()
		_, err := repo.Find(t.Context(), hashOf(9), now)
		require.ErrorIs(t, err, domain.ErrUserCredentialNotFound)
	})
}

func TestPostgresRotate(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping db tests in short mode.")
	}
	t.Parallel()

	signedInAt := now.Add(-10 * 24 * time.Hour)
	seed := func(t *testing.T, repo *Postgres) domain.UserCredential {
		t.Helper()
		cred := testCredential(1, "a937646bf11544c38dbf9ae4a65669a0")
		cred.ClientType = domain.MicrosoftClientPrism
		cred.CreatedAt = signedInAt
		cred.ExpiresAt = signedInAt.Add(idleWindow)
		require.NoError(t, repo.Insert(t.Context(), cred))
		return cred
	}

	t.Run("inserts the successor and puts the old row in its grace window", func(t *testing.T) {
		t.Parallel()
		repo, db, schema := newPostgres(t, "rotate")
		old := seed(t, repo)

		got, err := repo.Rotate(t.Context(), old.Hash, hashOf(2), now, grace, idleWindow)
		require.NoError(t, err)
		require.Equal(t, hashOf(2), got.Hash)
		require.Equal(t, old.IdentityKey, got.IdentityKey)
		require.Equal(t, domain.MicrosoftClientPrism, got.ClientType)
		require.True(t, signedInAt.Equal(got.CreatedAt), "created_at is when the Microsoft sign-in happened")
		require.True(t, now.Add(idleWindow).Equal(got.ExpiresAt))

		require.Len(t, readAll(t, db, schema), 2)
		successor := rowByHash(t, db, schema, hashOf(2))
		require.Equal(t, old.IdentityKey, successor.IdentityKey)
		require.Equal(t, "prism", successor.ClientType)
		require.True(t, signedInAt.Equal(successor.CreatedAt))
		require.True(t, now.Add(idleWindow).Equal(successor.ExpiresAt))
		require.NotNil(t, successor.LastUsedAt)
		require.True(t, now.Equal(*successor.LastUsedAt))

		retired := rowByHash(t, db, schema, old.Hash)
		require.True(t, now.Add(grace).Equal(retired.ExpiresAt))
		require.NotNil(t, retired.LastUsedAt)
		require.True(t, now.Equal(*retired.LastUsedAt))
	})

	t.Run("a grace row rotates again without extending its window", func(t *testing.T) {
		t.Parallel()
		repo, db, schema := newPostgres(t, "grace")
		old := seed(t, repo)

		_, err := repo.Rotate(t.Context(), old.Hash, hashOf(2), now, grace, idleWindow)
		require.NoError(t, err)
		later := now.Add(30 * time.Second)
		got, err := repo.Rotate(t.Context(), old.Hash, hashOf(3), later, grace, idleWindow)
		require.NoError(t, err)
		require.True(t, later.Add(idleWindow).Equal(got.ExpiresAt))

		require.Len(t, readAll(t, db, schema), 3)
		require.True(t, now.Add(grace).Equal(rowByHash(t, db, schema, old.Hash).ExpiresAt), "never re-slid")
	})

	t.Run("refuses a value presented after its grace window", func(t *testing.T) {
		t.Parallel()
		repo, db, schema := newPostgres(t, "stale")
		old := seed(t, repo)

		_, err := repo.Rotate(t.Context(), old.Hash, hashOf(2), now, grace, idleWindow)
		require.NoError(t, err)
		_, err = repo.Rotate(t.Context(), old.Hash, hashOf(3), now.Add(grace), grace, idleWindow)
		require.ErrorIs(t, err, domain.ErrUserCredentialStale)
		require.Len(t, readAll(t, db, schema), 2)
	})

	t.Run("refuses an idle-expired credential", func(t *testing.T) {
		t.Parallel()
		repo, db, schema := newPostgres(t, "idle")
		old := seed(t, repo)

		_, err := repo.Rotate(t.Context(), old.Hash, hashOf(2), old.ExpiresAt, grace, idleWindow)
		require.ErrorIs(t, err, domain.ErrUserCredentialStale)
		require.Len(t, readAll(t, db, schema), 1)
	})

	t.Run("refuses an unknown credential", func(t *testing.T) {
		t.Parallel()
		repo, db, schema := newPostgres(t, "unknown")

		_, err := repo.Rotate(t.Context(), hashOf(1), hashOf(2), now, grace, idleWindow)
		require.ErrorIs(t, err, domain.ErrUserCredentialNotFound)
		require.Empty(t, readAll(t, db, schema))
	})

	t.Run("refuses a malformed successor hash", func(t *testing.T) {
		t.Parallel()
		repo, db, schema := newPostgres(t, "malformed")
		old := seed(t, repo)

		_, err := repo.Rotate(t.Context(), old.Hash, []byte{2}, now, grace, idleWindow)
		require.Error(t, err)
		require.Len(t, readAll(t, db, schema), 1)
		require.True(t, old.ExpiresAt.Equal(rowByHash(t, db, schema, old.Hash).ExpiresAt))
	})

	t.Run("concurrent rotations of one value both succeed", func(t *testing.T) {
		t.Parallel()
		repo, db, schema := newPostgres(t, "concurrent")
		old := seed(t, repo)

		errs := make(chan error, 2)
		for _, next := range []byte{2, 3} {
			go func() {
				_, err := repo.Rotate(t.Context(), old.Hash, hashOf(next), now, grace, idleWindow)
				errs <- err
			}()
		}
		require.NoError(t, <-errs)
		require.NoError(t, <-errs)

		require.Len(t, readAll(t, db, schema), 3)
		require.True(t, now.Add(grace).Equal(rowByHash(t, db, schema, old.Hash).ExpiresAt))
	})

	t.Run("errors never quote the hash", func(t *testing.T) {
		t.Parallel()
		repo, _, _ := newPostgres(t, "quote")

		_, err := repo.Rotate(t.Context(), hashOf(0xab), hashOf(0xcd), now, grace, idleWindow)
		require.Error(t, err)
		require.NotContains(t, err.Error(), "abab")
		require.NotContains(t, err.Error(), "cdcd")
	})
}

func TestPostgresDeleteByIdentityOf(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping db tests in short mode.")
	}
	t.Parallel()

	const identity = "a937646bf11544c38dbf9ae4a65669a0"
	const other = "b937646bf11544c38dbf9ae4a65669a0"
	seed := func(t *testing.T, repo *Postgres) {
		t.Helper()
		require.NoError(t, repo.Insert(t.Context(), testCredential(1, identity)))
		prism := testCredential(2, identity)
		prism.ClientType = domain.MicrosoftClientPrism
		require.NoError(t, repo.Insert(t.Context(), prism))
		expired := testCredential(3, identity)
		expired.ExpiresAt = now
		require.NoError(t, repo.Insert(t.Context(), expired))
		require.NoError(t, repo.Insert(t.Context(), testCredential(4, other)))
	}

	t.Run("deletes every row for the identity and only those", func(t *testing.T) {
		t.Parallel()
		repo, db, schema := newPostgres(t, "logout")
		seed(t, repo)

		identityKey, deleted, err := repo.DeleteByIdentityOf(t.Context(), hashOf(2))
		require.NoError(t, err)
		require.Equal(t, identity, identityKey)
		require.Equal(t, 3, deleted, "includes other clients and expired rows")

		rows := readAll(t, db, schema)
		require.Len(t, rows, 1)
		require.Equal(t, other, rows[0].IdentityKey)
	})

	t.Run("a grace row still logs out", func(t *testing.T) {
		t.Parallel()
		repo, db, schema := newPostgres(t, "logoutgrace")
		seed(t, repo)
		_, err := repo.Rotate(t.Context(), hashOf(1), hashOf(5), now, grace, idleWindow)
		require.NoError(t, err)

		_, deleted, err := repo.DeleteByIdentityOf(t.Context(), hashOf(1))
		require.NoError(t, err)
		require.Equal(t, 4, deleted)
		require.Len(t, readAll(t, db, schema), 1)
	})

	t.Run("a stale credential still logs out", func(t *testing.T) {
		t.Parallel()
		repo, db, schema := newPostgres(t, "logoutstale")
		seed(t, repo)

		identityKey, deleted, err := repo.DeleteByIdentityOf(t.Context(), hashOf(3))
		require.NoError(t, err)
		require.Equal(t, identity, identityKey)
		require.Equal(t, 3, deleted)
		require.Len(t, readAll(t, db, schema), 1)
	})

	t.Run("concurrent logouts of one identity do not deadlock", func(t *testing.T) {
		t.Parallel()
		repo, db, schema := newPostgres(t, "logoutconcurrent")

		for range 20 {
			seed(t, repo)
			errs := make(chan error, 2)
			for _, hash := range [][]byte{hashOf(1), hashOf(2)} {
				go func() {
					_, _, err := repo.DeleteByIdentityOf(t.Context(), hash)
					if errors.Is(err, domain.ErrUserCredentialNotFound) {
						err = nil
					}
					errs <- err
				}()
			}
			require.NoError(t, <-errs)
			require.NoError(t, <-errs)
			require.Len(t, readAll(t, db, schema), 1)
			db.MustExec(fmt.Sprintf("DELETE FROM %s.user_credentials", pq.QuoteIdentifier(schema)))
		}
	})

	t.Run("a logout racing a rotation leaves no live credential", func(t *testing.T) {
		t.Parallel()
		repo, db, schema := newPostgres(t, "logoutrotate")

		for i := range 20 {
			seed(t, repo)
			done := make(chan error, 2)
			go func() {
				_, err := repo.Rotate(t.Context(), hashOf(2), hashOf(byte(100+i)), now, grace, idleWindow)
				if errors.Is(err, domain.ErrUserCredentialNotFound) {
					err = nil
				}
				done <- err
			}()
			go func() {
				_, _, err := repo.DeleteByIdentityOf(t.Context(), hashOf(1))
				done <- err
			}()
			require.NoError(t, <-done)
			require.NoError(t, <-done)

			rows := readAll(t, db, schema)
			require.Len(t, rows, 1, "the rotated successor is deleted too")
			require.Equal(t, other, rows[0].IdentityKey)
			db.MustExec(fmt.Sprintf("DELETE FROM %s.user_credentials", pq.QuoteIdentifier(schema)))
		}
	})

	t.Run("refuses an unknown credential and deletes nothing", func(t *testing.T) {
		t.Parallel()
		repo, db, schema := newPostgres(t, "logout_unknown")
		seed(t, repo)

		_, _, err := repo.DeleteByIdentityOf(t.Context(), hashOf(9))
		require.ErrorIs(t, err, domain.ErrUserCredentialNotFound)
		require.Len(t, readAll(t, db, schema), 4)
	})
}
