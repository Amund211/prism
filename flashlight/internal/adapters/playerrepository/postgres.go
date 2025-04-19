package playerrepository

import (
	"fmt"

	"github.com/jmoiron/sqlx"
	"github.com/lib/pq"
)

const DB_NAME = "flashlight"

const LOCAL_CONNECTION_STRING = "user=postgres password=postgres dbname=flashlight sslmode=disable"

func NewPostgresDatabase(connectionString string) (*sqlx.DB, error) {
	db, err := sqlx.Connect("postgres", connectionString)
	if err != nil {
		return nil, fmt.Errorf("NewPostgres: failed to connect to db: %w", err)
	}

	err = createDatabaseIfNotExists(db, DB_NAME)
	if err != nil {
		return nil, fmt.Errorf("NewPostgres: failed to create database: %w", err)
	}

	return db, nil
}

func createDatabaseIfNotExists(db *sqlx.DB, dbName string) error {
	row := db.QueryRowx("SELECT COUNT(*) FROM pg_database WHERE datname = $1", dbName)
	if row.Err() != nil {
		return fmt.Errorf("createDB: failed to check if database exists: %w", row.Err())
	}

	var count int
	if err := row.Scan(&count); err != nil {
		return fmt.Errorf("createDB: failed to scan row: %w", err)
	}

	if count > 0 {
		return nil
	}

	_, err := db.Exec(fmt.Sprintf("CREATE DATABASE %s", pq.QuoteIdentifier(dbName)))
	if err != nil {
		return fmt.Errorf("createDB: failed to create database: %w", err)
	}

	return nil
}
