// Package credentialrepository stores Microsoft-tier recovery credentials
// in user_credentials.
package credentialrepository

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"time"

	"github.com/jmoiron/sqlx"
	"github.com/lib/pq"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/trace"

	"github.com/Amund211/flashlight/internal/domain"
)

type Postgres struct {
	db     *sqlx.DB
	schema string
	tracer trace.Tracer
}

func NewPostgres(db *sqlx.DB, schema string) *Postgres {
	return &Postgres{
		db:     db,
		schema: schema,
		tracer: otel.Tracer("flashlight/credentialrepository/postgres"),
	}
}

// Insert stores a new credential. Errors never quote the hash.
func (p *Postgres) Insert(ctx context.Context, cred domain.UserCredential) error {
	ctx, span := p.tracer.Start(ctx, "Postgres.Insert")
	defer span.End()

	if len(cred.Hash) != domain.UserCredentialHashLength || cred.IdentityKey == "" || !cred.ClientType.IsKnown() || cred.CreatedAt.IsZero() || cred.ExpiresAt.IsZero() {
		return fmt.Errorf("refusing to insert an incomplete credential")
	}

	_, err := p.db.ExecContext(
		ctx,
		fmt.Sprintf(`INSERT INTO %s.user_credentials
		(credential_hash, identity_key, client_type, created_at, expires_at)
		VALUES ($1, $2, $3, $4, $5)`,
			pq.QuoteIdentifier(p.schema)),
		cred.Hash,
		cred.IdentityKey,
		string(cred.ClientType),
		cred.CreatedAt,
		cred.ExpiresAt,
	)
	if err != nil {
		return fmt.Errorf("failed to insert credential: %w", err)
	}
	return nil
}

type credentialRow struct {
	CredentialHash []byte    `db:"credential_hash"`
	IdentityKey    string    `db:"identity_key"`
	ClientType     string    `db:"client_type"`
	CreatedAt      time.Time `db:"created_at"`
	ExpiresAt      time.Time `db:"expires_at"`
}

func (r credentialRow) toDomain() domain.UserCredential {
	return domain.UserCredential{
		Hash:        r.CredentialHash,
		IdentityKey: r.IdentityKey,
		ClientType:  domain.MicrosoftClientType(r.ClientType),
		CreatedAt:   r.CreatedAt,
		ExpiresAt:   r.ExpiresAt,
	}
}

// get reads one row, and refuses it unless it is live at now.
func (p *Postgres) get(ctx context.Context, q sqlx.QueryerContext, hash []byte, now time.Time, forUpdate bool) (credentialRow, error) {
	query := fmt.Sprintf(`SELECT credential_hash, identity_key, client_type, created_at, expires_at
		FROM %s.user_credentials WHERE credential_hash = $1`, pq.QuoteIdentifier(p.schema))
	if forUpdate {
		query += " FOR UPDATE"
	}

	var row credentialRow
	err := sqlx.GetContext(ctx, q, &row, query, hash)
	if errors.Is(err, sql.ErrNoRows) {
		return credentialRow{}, domain.ErrUserCredentialNotFound
	}
	if err != nil {
		return credentialRow{}, fmt.Errorf("failed to read credential: %w", err)
	}
	if !now.Before(row.ExpiresAt) {
		return credentialRow{}, domain.ErrUserCredentialStale
	}
	return row, nil
}

// Find returns the live credential with this hash, or
// domain.ErrUserCredentialNotFound / domain.ErrUserCredentialStale.
func (p *Postgres) Find(ctx context.Context, hash []byte, now time.Time) (domain.UserCredential, error) {
	ctx, span := p.tracer.Start(ctx, "Postgres.Find")
	defer span.End()

	row, err := p.get(ctx, p.db, hash, now, false)
	if err != nil {
		return domain.UserCredential{}, err
	}
	return row.toDomain(), nil
}

// Rotate replaces the live credential presentedHash with newHash, which
// expires at now + idleWindow. The presented row stays valid until
// now + grace, and a row already in its grace window is never extended.
// Returns the new credential, or the errors Find returns.
func (p *Postgres) Rotate(ctx context.Context, presentedHash, newHash []byte, now time.Time, grace, idleWindow time.Duration) (domain.UserCredential, error) {
	ctx, span := p.tracer.Start(ctx, "Postgres.Rotate")
	defer span.End()

	if len(newHash) != domain.UserCredentialHashLength {
		return domain.UserCredential{}, fmt.Errorf("refusing to rotate to a malformed hash")
	}

	tx, err := p.db.BeginTxx(ctx, nil)
	if err != nil {
		return domain.UserCredential{}, fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer func() { _ = tx.Rollback() }()

	old, err := p.get(ctx, tx, presentedHash, now, true)
	if err != nil {
		return domain.UserCredential{}, err
	}

	next := domain.UserCredential{
		Hash:        newHash,
		IdentityKey: old.IdentityKey,
		ClientType:  domain.MicrosoftClientType(old.ClientType),
		CreatedAt:   old.CreatedAt,
		ExpiresAt:   now.Add(idleWindow),
	}
	_, err = tx.ExecContext(
		ctx,
		fmt.Sprintf(`INSERT INTO %s.user_credentials
		(credential_hash, identity_key, client_type, created_at, expires_at, last_used_at)
		VALUES ($1, $2, $3, $4, $5, $6)`,
			pq.QuoteIdentifier(p.schema)),
		next.Hash,
		next.IdentityKey,
		string(next.ClientType),
		next.CreatedAt,
		next.ExpiresAt,
		now,
	)
	if err != nil {
		return domain.UserCredential{}, fmt.Errorf("failed to insert rotated credential: %w", err)
	}

	// LEAST: re-sliding a grace row would make the stale value a second
	// live credential.
	_, err = tx.ExecContext(
		ctx,
		fmt.Sprintf(`UPDATE %s.user_credentials
		SET expires_at = LEAST(expires_at, $2), last_used_at = $3
		WHERE credential_hash = $1`,
			pq.QuoteIdentifier(p.schema)),
		presentedHash,
		now.Add(grace),
		now,
	)
	if err != nil {
		return domain.UserCredential{}, fmt.Errorf("failed to retire credential: %w", err)
	}

	if err := tx.Commit(); err != nil {
		return domain.UserCredential{}, fmt.Errorf("failed to commit rotation: %w", err)
	}
	return next, nil
}

// DeleteByIdentityOf deletes every credential of the identity that holds
// the live credential hash, expired rows included. Returns that identity
// and the number of rows deleted, or the errors Find returns.
func (p *Postgres) DeleteByIdentityOf(ctx context.Context, hash []byte, now time.Time) (string, int, error) {
	ctx, span := p.tracer.Start(ctx, "Postgres.DeleteByIdentityOf")
	defer span.End()

	tx, err := p.db.BeginTxx(ctx, nil)
	if err != nil {
		return "", 0, fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer func() { _ = tx.Rollback() }()

	row, err := p.get(ctx, tx, hash, now, true)
	if err != nil {
		return "", 0, err
	}

	result, err := tx.ExecContext(
		ctx,
		fmt.Sprintf(`DELETE FROM %s.user_credentials WHERE identity_key = $1`, pq.QuoteIdentifier(p.schema)),
		row.IdentityKey,
	)
	if err != nil {
		return "", 0, fmt.Errorf("failed to delete credentials: %w", err)
	}
	deleted, err := result.RowsAffected()
	if err != nil {
		return "", 0, fmt.Errorf("failed to count deleted credentials: %w", err)
	}

	if err := tx.Commit(); err != nil {
		return "", 0, fmt.Errorf("failed to commit logout: %w", err)
	}
	return row.IdentityKey, int(deleted), nil
}
