package database

import (
	"context"
	"embed"
	"errors"
	"fmt"
	"log/slog"

	"github.com/golang-migrate/migrate/v4"
	"github.com/golang-migrate/migrate/v4/database/postgres"
	"github.com/golang-migrate/migrate/v4/source/iofs"
	"github.com/jmoiron/sqlx"
	"github.com/lib/pq"
)

//go:embed migrations/*.sql
var embeddedMigrations embed.FS

type migrator struct {
	db *sqlx.DB

	logger *slog.Logger
}

func NewDatabaseMigrator(db *sqlx.DB, logger *slog.Logger) *migrator {
	return &migrator{
		db:     db,
		logger: logger,
	}
}

func (m *migrator) Migrate(ctx context.Context, schemaName string) error {
	return m.migrate(ctx, schemaName)
}

func (m *migrator) migrate(ctx context.Context, schemaName string) error {
	conn, err := m.db.Conn(ctx)
	if err != nil {
		return fmt.Errorf("migrate: failed to connect to db: %w", err)
	}
	defer conn.Close()

	_, err = conn.ExecContext(ctx, fmt.Sprintf("CREATE SCHEMA IF NOT EXISTS %s", pq.QuoteIdentifier(schemaName)))
	if err != nil {
		return fmt.Errorf("migrate: failed to create schema: %w", err)
	}

	_, err = conn.ExecContext(ctx, fmt.Sprintf("SET search_path TO %s", pq.QuoteIdentifier(schemaName)))
	if err != nil {
		return fmt.Errorf("migrate: failed to set search path: %w", err)
	}

	migrationSource, err := iofs.New(embeddedMigrations, "migrations")
	if err != nil {
		return fmt.Errorf("migrate: failed to create driver from embedded migrations: %w", err)
	}
	defer migrationSource.Close()

	dbDriver, err := postgres.WithConnection(ctx, conn, &postgres.Config{
		DatabaseName: DB_NAME,
		SchemaName:   schemaName,
	})
	if err != nil {
		return fmt.Errorf("migrate: failed to create postgres driver: %w", err)
	}

	migratorInstance, err := migrate.NewWithInstance("iofs", migrationSource, "postgres", dbDriver)
	if err != nil {
		return fmt.Errorf("migrate: failed to create migration instance: %w", err)
	}
	defer migratorInstance.Close()

	m.logger.Info("Starting migrations...")
	if err := migratorInstance.Up(); err != nil {
		if errors.Is(err, migrate.ErrNoChange) {
			m.logger.Info("No migrations to run.")
		} else {
			return fmt.Errorf("migrate: failed to migrate: %w", err)
		}
	}
	m.logger.Info("Migrations completed successfully.")

	return nil
}
