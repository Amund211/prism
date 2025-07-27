package usernamerepository

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/strutils"
	"github.com/jmoiron/sqlx"
	"github.com/lib/pq"
)

type PostgresUsernameRepository struct {
	db     *sqlx.DB
	schema string
}

func NewPostgresUsernameRepository(db *sqlx.DB, schema string) *PostgresUsernameRepository {
	return &PostgresUsernameRepository{db, schema}
}

type dbUsernamesEntry struct {
	PlayerUUID string    `db:"player_uuid"`
	Username   string    `db:"username"`
	QueriedAt  time.Time `db:"queried_at"`
}

type dbUsernameQueriesEntry struct {
	PlayerUUID    string    `db:"player_uuid"`
	Username      string    `db:"username"`
	LastQueriedAt time.Time `db:"last_queried_at"`
}

func (p *PostgresUsernameRepository) StoreUsername(ctx context.Context, uuid string, queriedAt time.Time, username string) error {
	if !strutils.UUIDIsNormalized(uuid) {
		err := fmt.Errorf("uuid is not normalized")
		reporting.Report(ctx, err, map[string]string{
			"uuid": uuid,
		})
		return err
	}

	txx, err := p.db.BeginTxx(ctx, nil)
	if err != nil {
		err := fmt.Errorf("failed to start transaction: %w", err)
		reporting.Report(ctx, err)
		return err
	}
	defer txx.Rollback()

	_, err = txx.ExecContext(ctx, fmt.Sprintf("SET search_path TO %s", pq.QuoteIdentifier(p.schema)))
	if err != nil {
		err := fmt.Errorf("failed to set search path: %w", err)
		reporting.Report(ctx, err, map[string]string{
			"schema": p.schema,
		})
		return err
	}

	// Insert or update entry in username_queries table
	_, err = txx.ExecContext(
		ctx,
		`INSERT INTO username_queries
		(player_uuid, username, last_queried_at)
		VALUES ($1, $2, $3)
		ON CONFLICT (player_uuid, username)
		DO UPDATE SET
			last_queried_at = EXCLUDED.last_queried_at`,
		uuid,
		username,
		queriedAt,
	)
	if err != nil {
		err := fmt.Errorf("failed to insert or update username_queries entry: %w", err)
		reporting.Report(ctx, err, map[string]string{
			"uuid":          uuid,
			"username":      username,
			"lastQueriedAt": queriedAt.Format(time.RFC3339),
		})
		return err
	}

	// Ensure exclusive access to the usernames table to prevent concurrent writes
	// leading to unique constraint violations
	//
	// NOTE: Using level EXCLUSIVE allows concurrent reads. This can result in misses if a
	// read occurs between the delete and upsert operations.
	// This will only occur if an already existing username is being assigned to a different UUID,
	// which is hopefully an uncommon case.
	//
	// https://www.postgresql.org/docs/current/explicit-locking.html#LOCKING-TABLES
	_, err = txx.ExecContext(ctx, "LOCK TABLE usernames IN EXCLUSIVE MODE")
	if err != nil {
		err := fmt.Errorf("failed to lock usernames table: %w", err)
		reporting.Report(ctx, err)
		return err
	}

	// Remove existing entries with same username case insensitively
	// NOTE: Not deleting entries with the same UUID, as we will update it later if it exists
	_, err = txx.ExecContext(ctx, "DELETE FROM usernames WHERE lower(username) = lower($1) AND player_uuid != $2", username, uuid)
	if err != nil {
		err := fmt.Errorf("failed to delete entries with given username (case insensitive): %w", err)
		reporting.Report(ctx, err, map[string]string{
			"username": username,
		})
		return err
	}

	// Insert new entry in usernames table
	_, err = txx.ExecContext(
		ctx,
		`INSERT INTO usernames
		(player_uuid, username, queried_at)
		VALUES ($1, $2, $3)
		ON CONFLICT (player_uuid)
		DO UPDATE SET
			username = EXCLUDED.username,
			queried_at = EXCLUDED.queried_at`,
		uuid,
		username,
		queriedAt,
	)
	if err != nil {
		err := fmt.Errorf("failed to upsert new usernames entry: %w", err)
		reporting.Report(ctx, err, map[string]string{
			"uuid":      uuid,
			"username":  username,
			"queriedAt": queriedAt.Format(time.RFC3339),
		})
		return err
	}

	err = txx.Commit()
	if err != nil {
		err := fmt.Errorf("failed to commit transaction: %w", err)
		reporting.Report(ctx, err)
		return err
	}

	return nil
}

func (p *PostgresUsernameRepository) RemoveUsername(ctx context.Context, username string) error {
	_, err := p.db.ExecContext(ctx, fmt.Sprintf(`
			DELETE FROM %s.usernames
			WHERE lower(username) = lower($1)`,
		pq.QuoteIdentifier(p.schema),
	),
		username,
	)
	if err != nil {
		err := fmt.Errorf("failed to delete username (case insensitive): %w", err)
		reporting.Report(ctx, err, map[string]string{
			"username": username,
		})
		return err
	}

	return nil
}

func (p *PostgresUsernameRepository) GetUsername(ctx context.Context, uuid string) (username string, queriedAt time.Time, err error) {
	if !strutils.UUIDIsNormalized(uuid) {
		err := fmt.Errorf("uuid is not normalized")
		reporting.Report(ctx, err, map[string]string{
			"uuid": uuid,
		})
		return "", time.Time{}, err
	}

	var entry dbUsernamesEntry
	err = p.db.GetContext(ctx, &entry, fmt.Sprintf(`SELECT
		player_uuid, username, queried_at
		FROM %s.usernames
		WHERE player_uuid = $1`,
		pq.QuoteIdentifier(p.schema),
	),
		uuid,
	)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			// No entry found
			return "", time.Time{}, domain.ErrUsernameNotFound
		}
		err := fmt.Errorf("failed to select usernames entry: %w", err)
		reporting.Report(ctx, err, map[string]string{
			"uuid": uuid,
		})
		return "", time.Time{}, err
	}

	return entry.Username, entry.QueriedAt, nil
}

func (p *PostgresUsernameRepository) GetUUID(ctx context.Context, username string) (uuid string, queriedAt time.Time, err error) {
	var entry dbUsernamesEntry
	err = p.db.GetContext(ctx, &entry, fmt.Sprintf(`SELECT
		player_uuid, username, queried_at
		FROM %s.usernames
		WHERE lower(username) = lower($1)`,
		pq.QuoteIdentifier(p.schema),
	),
		username,
	)
	if err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			// No entry found
			return "", time.Time{}, domain.ErrUsernameNotFound
		}
		err := fmt.Errorf("failed to select usernames entry: %w", err)
		reporting.Report(ctx, err, map[string]string{
			"username": username,
		})
		return "", time.Time{}, err
	}

	if !strutils.UUIDIsNormalized(entry.PlayerUUID) {
		err := fmt.Errorf("uuid is not normalized")
		reporting.Report(ctx, err, map[string]string{
			"uuid": entry.PlayerUUID,
		})
		return "", time.Time{}, err
	}

	return entry.PlayerUUID, entry.QueriedAt, nil
}
