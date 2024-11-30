package storage

import (
	"context"
	"fmt"
	"time"

	"github.com/Amund211/flashlight/internal/strutils"
	"github.com/google/uuid"
	"github.com/jmoiron/sqlx"
	"github.com/lib/pq"
)

type StatsPersistor interface {
	StoreStats(ctx context.Context, playerUUID string, playerData []byte, queriedAt time.Time) error
}

type PostgresStatsPersistor struct {
	db     *sqlx.DB
	schema string
}

const MAIN_SCHEMA = "flashlight"
const TESTING_SCHEMA = "flashlight_test"

func GetSchemaName(isTesting bool) string {
	if isTesting {
		return TESTING_SCHEMA
	}
	return MAIN_SCHEMA
}

func NewPostgresStatsPersistor(db *sqlx.DB, schema string) *PostgresStatsPersistor {
	return &PostgresStatsPersistor{db, schema}
}

func (p *PostgresStatsPersistor) StoreStats(ctx context.Context, playerUUID string, playerData []byte, queriedAt time.Time) error {
	normalizedUUID, err := strutils.NormalizeUUID(playerUUID)
	if err != nil {
		return fmt.Errorf("StoreStats: failed to normalize uuid: %w", err)
	}

	dbID, err := uuid.NewV7()
	if err != nil {
		return fmt.Errorf("StoreStats: failed to generate uuid: %w", err)
	}

	txx, err := p.db.BeginTxx(ctx, nil)
	if err != nil {
		return fmt.Errorf("StoreStats: failed to start transaction: %w", err)
	}
	defer txx.Rollback()

	_, err = txx.ExecContext(ctx, fmt.Sprintf("SET search_path TO %s", pq.QuoteIdentifier(p.schema)))
	if err != nil {
		return fmt.Errorf("StoreStats: failed to set search path: %w", err)
	}

	_, err = txx.Exec("INSERT INTO stats (id, player_uuid, player_data, queried_at) VALUES ($1, $2, $3, $4)", dbID.String(), normalizedUUID, playerData, queriedAt)
	if err != nil {
		return fmt.Errorf("StoreStats: failed to insert stats: %w", err)
	}

	err = txx.Commit()
	if err != nil {
		return fmt.Errorf("StoreStats: failed to commit transaction: %w", err)
	}
	return err
}

type StubPersistor struct{}

func (p *StubPersistor) StoreStats(ctx context.Context, playerUUID string, playerData []byte, queriedAt time.Time) error {
	return nil
}

func NewStubPersistor() *StubPersistor {
	return &StubPersistor{}
}
