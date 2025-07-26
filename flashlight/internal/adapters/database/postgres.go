package database

import (
	"fmt"

	"github.com/Amund211/flashlight/internal/config"
	"github.com/jmoiron/sqlx"
	"github.com/lib/pq"
)

const DB_NAME = "flashlight"

const LOCAL_CONNECTION_STRING = "user=postgres password=postgres dbname=flashlight sslmode=disable"

const MAIN_SCHEMA = "flashlight"
const TESTING_SCHEMA = "flashlight_test"

func GetSchemaName(isTesting bool) string {
	if isTesting {
		return TESTING_SCHEMA
	}
	return MAIN_SCHEMA
}

func NewPostgresDatabase(connectionString string) (*sqlx.DB, error) {
	db, err := sqlx.Connect("postgres", connectionString)
	if err != nil {
		return nil, fmt.Errorf("failed to connect to db: %w", err)
	}

	err = createDatabaseIfNotExists(db, DB_NAME)
	if err != nil {
		return nil, fmt.Errorf("failed to create database: %w", err)
	}

	return db, nil
}

func NewCloudsqlPostgresDatabase(conf config.Config) (*sqlx.DB, error) {
	var connectionString string
	if conf.IsDevelopment() {
		connectionString = LOCAL_CONNECTION_STRING
	} else {
		connectionString = GetCloudSQLConnectionString(conf.DBUsername(), conf.DBPassword(), conf.CloudSQLUnixSocketPath())
	}

	db, err := NewPostgresDatabase(connectionString)
	if err != nil {
		return nil, fmt.Errorf("failed to create postgres database: %w", err)
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
