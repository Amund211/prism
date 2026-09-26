package credentialrepository

import (
	"bytes"
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
