package database

import (
	"fmt"
	"log/slog"
	"os"
	"testing"

	"github.com/golang-migrate/migrate/v4"
	"github.com/golang-migrate/migrate/v4/database/postgres"
	"github.com/golang-migrate/migrate/v4/source/iofs"
	"github.com/lib/pq"
	"github.com/stretchr/testify/require"
)

func TestMigrator(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping migrator tests in short mode.")
	}
	t.Parallel()

	t.Run("migrate up and down", func(t *testing.T) {
		t.Parallel()

		ctx := t.Context()
		schemaName := "migrate_up_down"

		db, err := NewPostgresDatabase(LOCAL_CONNECTION_STRING)
		require.NoError(t, err)

		db.MustExec(fmt.Sprintf("DROP SCHEMA IF EXISTS %s CASCADE", pq.QuoteIdentifier(schemaName)))

		logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
		migrator := NewDatabaseMigrator(db, logger)

		err = migrator.migrate(ctx, schemaName)
		require.NoError(t, err, "error migrating up")

		// Migrate down manually
		conn, err := db.Conn(ctx)
		require.NoError(t, err)
		defer conn.Close()
		_, err = conn.ExecContext(ctx, fmt.Sprintf("SET search_path TO %s", pq.QuoteIdentifier(schemaName)))
		require.NoError(t, err)

		migrationSource, err := iofs.New(embeddedMigrations, "migrations")
		require.NoError(t, err)
		defer migrationSource.Close()

		dbDriver, err := postgres.WithConnection(ctx, conn, &postgres.Config{
			DatabaseName: DB_NAME,
			SchemaName:   schemaName,
		})
		require.NoError(t, err)

		migratorInstance, err := migrate.NewWithInstance("iofs", migrationSource, "postgres", dbDriver)
		require.NoError(t, err)
		defer migratorInstance.Close()

		err = migratorInstance.Down()
		require.NoError(t, err, "error migrating down") // Should not even be ErrNoChange
	})
}
