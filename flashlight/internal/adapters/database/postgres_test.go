package database

import (
	"fmt"
	"math/rand"
	"testing"

	"github.com/jmoiron/sqlx"
	"github.com/stretchr/testify/require"
)

func TestDB(t *testing.T) {
	t.Parallel()

	t.Run("db name", func(t *testing.T) {
		t.Parallel()

		require.Equal(t, "flashlight", DB_NAME)
	})

	if testing.Short() {
		t.Skip("skipping db tests in short mode.")
	}

	t.Run("NewPostgresDatabase", func(t *testing.T) {
		t.Parallel()

		db, err := NewPostgresDatabase(LOCAL_CONNECTION_STRING)
		require.NoError(t, err)
		require.NotNil(t, db)
	})

	t.Run("createDatabaseIfNotExists", func(t *testing.T) {
		t.Parallel()

		db, err := sqlx.Connect("postgres", LOCAL_CONNECTION_STRING)
		require.NoError(t, err)
		t.Run("already existing", func(t *testing.T) {
			t.Parallel()

			err := createDatabaseIfNotExists(db, "postgres")
			require.NoError(t, err)

			err = createDatabaseIfNotExists(db, DB_NAME)
			require.NoError(t, err)
		})

		t.Run("new database", func(t *testing.T) {
			t.Parallel()

			const characters = "abcdefghijklmnopqrstuvwxyz"
			bytes := make([]byte, 10)
			for i := range bytes {
				bytes[i] = characters[rand.Intn(len(characters))]
			}

			dbName := fmt.Sprintf("zz_random_db_%s", string(bytes))

			err := createDatabaseIfNotExists(db, dbName)
			require.NoError(t, err)
		})
	})
}
