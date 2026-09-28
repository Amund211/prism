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

	return p.insert(ctx, p.db, cred, nil)
}

func (p *Postgres) insert(ctx context.Context, e sqlx.ExecerContext, cred domain.UserCredential, lastUsedAt *time.Time) error {
	if len(cred.Hash) != domain.UserCredentialHashLength || cred.IdentityKey == "" || !cred.ClientType.IsKnown() || cred.CreatedAt.IsZero() || cred.ExpiresAt.IsZero() {
		return fmt.Errorf("refusing to insert an incomplete credential")
	}

	_, err := e.ExecContext(
		ctx,
		fmt.Sprintf(`INSERT INTO %s.user_credentials
		(credential_hash, identity_key, client_type, created_at, expires_at, last_used_at)
		VALUES ($1, $2, $3, $4, $5, $6)`,
			pq.QuoteIdentifier(p.schema)),
		cred.Hash,
		cred.IdentityKey,
		string(cred.ClientType),
		cred.CreatedAt,
		cred.ExpiresAt,
		lastUsedAt,
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

func (p *Postgres) get(ctx context.Context, q sqlx.QueryerContext, hash []byte) (credentialRow, error) {
	var row credentialRow
	err := sqlx.GetContext(ctx, q, &row, fmt.Sprintf(`SELECT credential_hash, identity_key, client_type, created_at, expires_at
		FROM %s.user_credentials WHERE credential_hash = $1`, pq.QuoteIdentifier(p.schema)), hash)
	if errors.Is(err, sql.ErrNoRows) {
		return credentialRow{}, domain.ErrUserCredentialNotFound
	}
	if err != nil {
		return credentialRow{}, fmt.Errorf("failed to read credential: %w", err)
	}
	return row, nil
}

func (p *Postgres) getLive(ctx context.Context, q sqlx.QueryerContext, hash []byte, now time.Time) (credentialRow, error) {
	row, err := p.get(ctx, q, hash)
	if err != nil {
		return credentialRow{}, err
	}
	if !now.Before(row.ExpiresAt) {
		return credentialRow{}, domain.ErrUserCredentialStale
	}
	return row, nil
}

// Without it a logout misses a successor inserted mid-DELETE, and two
// logouts deadlock on each other's row locks. Take it before any row lock.
func lockIdentity(ctx context.Context, tx *sqlx.Tx, identityKey string) error {
	if _, err := tx.ExecContext(ctx, "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", identityKey); err != nil {
		return fmt.Errorf("failed to lock identity: %w", err)
	}
	return nil
}

// Find returns the live credential with this hash, or
// domain.ErrUserCredentialNotFound / domain.ErrUserCredentialStale.
func (p *Postgres) Find(ctx context.Context, hash []byte, now time.Time) (domain.UserCredential, error) {
	ctx, span := p.tracer.Start(ctx, "Postgres.Find")
	defer span.End()

	row, err := p.getLive(ctx, p.db, hash, now)
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

	tx, err := p.db.BeginTxx(ctx, nil)
	if err != nil {
		return domain.UserCredential{}, fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer func() { _ = tx.Rollback() }()

	unlocked, err := p.get(ctx, tx, presentedHash)
	if err != nil {
		return domain.UserCredential{}, err
	}
	if err := lockIdentity(ctx, tx, unlocked.IdentityKey); err != nil {
		return domain.UserCredential{}, err
	}
	// Read again under the lock: a logout or a rotation may have committed.
	old, err := p.getLive(ctx, tx, presentedHash, now)
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
	if err := p.insert(ctx, tx, next, &now); err != nil {
		return domain.UserCredential{}, err
	}

	// LEAST: re-sliding a grace row would keep the old value alive forever.
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

// ListActive returns one entry per Microsoft sign-in of the identity that
// still has a live credential, newest first. A sign-in is (client_type,
// created_at): rotation copies both, so a grace row and racing successors
// fold into the sign-in they came from.
func (p *Postgres) ListActive(ctx context.Context, identityKey string, now time.Time) ([]domain.ActiveSignIn, error) {
	ctx, span := p.tracer.Start(ctx, "Postgres.ListActive")
	defer span.End()

	var rows []struct {
		ClientType string    `db:"client_type"`
		CreatedAt  time.Time `db:"created_at"`
		LastUsedAt time.Time `db:"last_used_at"`
	}
	err := sqlx.SelectContext(ctx, p.db, &rows, fmt.Sprintf(`SELECT client_type, created_at, MAX(COALESCE(last_used_at, created_at)) AS last_used_at
		FROM %s.user_credentials
		WHERE identity_key = $1 AND expires_at > $2
		GROUP BY client_type, created_at
		ORDER BY created_at DESC, last_used_at DESC`, pq.QuoteIdentifier(p.schema)), identityKey, now)
	if err != nil {
		return nil, fmt.Errorf("failed to list credentials: %w", err)
	}

	signIns := make([]domain.ActiveSignIn, 0, len(rows))
	for _, row := range rows {
		signIns = append(signIns, domain.ActiveSignIn{
			ClientType: domain.MicrosoftClientType(row.ClientType),
			CreatedAt:  row.CreatedAt,
			LastUsedAt: row.LastUsedAt,
		})
	}
	return signIns, nil
}

// DeleteByIdentityOf deletes every credential of the identity that holds
// the credential hash, live or not, expired rows included. Returns that
// identity and the number of rows deleted, or
// domain.ErrUserCredentialNotFound.
func (p *Postgres) DeleteByIdentityOf(ctx context.Context, hash []byte) (string, int, error) {
	ctx, span := p.tracer.Start(ctx, "Postgres.DeleteByIdentityOf")
	defer span.End()

	tx, err := p.db.BeginTxx(ctx, nil)
	if err != nil {
		return "", 0, fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer func() { _ = tx.Rollback() }()

	row, err := p.get(ctx, tx, hash)
	if err != nil {
		return "", 0, err
	}
	if err := lockIdentity(ctx, tx, row.IdentityKey); err != nil {
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
