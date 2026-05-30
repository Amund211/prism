package authsessionrepository

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
	"github.com/Amund211/flashlight/internal/reporting"
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
		tracer: otel.Tracer("flashlight/authsessionrepository/postgres"),
	}
}

type dbAuthSession struct {
	ID             string       `db:"id"`
	IdentityType   string       `db:"identity_type"`
	IdentityKey    string       `db:"identity_key"`
	IPHash         string       `db:"ip_hash"`
	CreatedAt      time.Time    `db:"created_at"`
	ExpiresAt      time.Time    `db:"expires_at"`
	RefreshUntil   time.Time    `db:"refresh_until"`
	LifetimeEndsAt time.Time    `db:"lifetime_ends_at"`
	LastUsedAt     time.Time    `db:"last_used_at"`
	RevokedAt      sql.NullTime `db:"revoked_at"`
}

// dbIdentityType is the on-disk representation of an identity type.
type dbIdentityType string

const dbIdentityTypeAnonymous dbIdentityType = "anonymous"

// Revoked-reason values written to the revoked_reason column. These
// are DB-only audit data — not surfaced on the domain model and not
// returned to clients — so they live here next to the SQL that writes
// them.
const (
	revokedReasonReplaced       = "replaced"
	revokedReasonExpired        = "expired"
	revokedReasonEvictedByIPCap = "evicted_by_ip_cap"
)

func identityTypeFromDB(s string) (domain.AuthSessionIdentityType, error) {
	switch dbIdentityType(s) {
	case dbIdentityTypeAnonymous:
		return domain.AuthSessionIdentityAnonymous, nil
	default:
		return "", fmt.Errorf("unknown identity_type in db: %q", s)
	}
}

func identityTypeToDB(t domain.AuthSessionIdentityType) (string, error) {
	switch t {
	case domain.AuthSessionIdentityAnonymous:
		return string(dbIdentityTypeAnonymous), nil
	default:
		return "", fmt.Errorf("unknown identity type: %q", string(t))
	}
}

func (r dbAuthSession) toDomain() (domain.AuthSession, error) {
	identityType, err := identityTypeFromDB(r.IdentityType)
	if err != nil {
		return domain.AuthSession{}, fmt.Errorf("failed to decode identity type from db: %w", err)
	}
	var revokedAt *time.Time
	if r.RevokedAt.Valid {
		t := r.RevokedAt.Time
		revokedAt = &t
	}
	return domain.AuthSession{
		ID:             r.ID,
		IdentityType:   identityType,
		IdentityKey:    r.IdentityKey,
		IPHash:         r.IPHash,
		CreatedAt:      r.CreatedAt,
		ExpiresAt:      r.ExpiresAt,
		RefreshUntil:   r.RefreshUntil,
		LifetimeEndsAt: r.LifetimeEndsAt,
		LastUsedAt:     r.LastUsedAt,
		RevokedAt:      revokedAt,
	}, nil
}

// Create inserts a complete session into the table. The caller is
// responsible for filling in every field, including a unique ID and a
// last_used_at value (typically set to created_at on initial issue).
//
// Single-active-per-identity is enforced by soft-revoking any existing
// active row for the same (identity_type, identity_key) in the same
// transaction. The reason recorded on the old row is:
//   - "replaced" if it was still within its refresh window
//   - "expired"  if it had already aged past it
//
// revoked_at follows the reason: "replaced" rows get the current time
// (the session was actively killed now), "expired" rows get their own
// expires_at (the session was provably unused after that point — any
// later validate would have failed and any later refresh would have
// moved expires_at forward, so a row that aged out to refresh_until
// without being refreshed cannot have been used past expires_at).
// Note: rows that never get touched by Create/EnforceActiveIPCap can
// still sit with revoked_at IS NULL past their refresh_until — for
// those, the row's expires_at / lifetime_ends_at are the truth.
func (p *Postgres) Create(ctx context.Context, sess domain.AuthSession) error {
	ctx, span := p.tracer.Start(ctx, "Postgres.Create")
	defer span.End()

	identityTypeDB, err := identityTypeToDB(sess.IdentityType)
	if err != nil {
		err := fmt.Errorf("failed to encode identity type for create: %w", err)
		reporting.Report(ctx, err)
		return err
	}

	tx, err := p.db.BeginTxx(ctx, nil)
	if err != nil {
		err := fmt.Errorf("failed to begin tx for create: %w", err)
		reporting.Report(ctx, err)
		return err
	}
	defer tx.Rollback()

	// Soft-revoke any existing active row for this identity. Both the
	// reason and the revoked_at timestamp depend on whether the row
	// was still within its refresh window: an actively-killed row gets
	// the current time, an already-aged-out row gets its own
	// expires_at (the last point at which the session was provably
	// usable).
	_, err = tx.ExecContext(
		ctx,
		fmt.Sprintf(`UPDATE %s.auth_sessions
		SET revoked_at = CASE WHEN refresh_until > $1 THEN $1 ELSE expires_at END,
		    revoked_reason = CASE WHEN refresh_until > $1 THEN $2 ELSE $3 END
		WHERE identity_type = $4 AND identity_key = $5 AND revoked_at IS NULL`,
			pq.QuoteIdentifier(p.schema)),
		sess.CreatedAt,
		revokedReasonReplaced,
		revokedReasonExpired,
		identityTypeDB,
		sess.IdentityKey,
	)
	if err != nil {
		err := fmt.Errorf("failed to revoke existing active session: %w", err)
		reporting.Report(ctx, err)
		return err
	}

	_, err = tx.ExecContext(
		ctx,
		fmt.Sprintf(`INSERT INTO %s.auth_sessions
		(id, identity_type, identity_key, ip_hash, created_at, expires_at, refresh_until, lifetime_ends_at, last_used_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)`,
			pq.QuoteIdentifier(p.schema)),
		sess.ID,
		identityTypeDB,
		sess.IdentityKey,
		sess.IPHash,
		sess.CreatedAt,
		sess.ExpiresAt,
		sess.RefreshUntil,
		sess.LifetimeEndsAt,
		sess.LastUsedAt,
	)
	if err != nil {
		err := fmt.Errorf("failed to insert auth session: %w", err)
		reporting.Report(ctx, err)
		return err
	}

	if err := tx.Commit(); err != nil {
		err := fmt.Errorf("failed to commit create: %w", err)
		reporting.Report(ctx, err)
		return err
	}
	return nil
}

// Update loads the row by id, calls update on it, and writes the
// result back inside a single transaction. update sees the live row
// and returns the desired new state. The row is SELECT-FOR-UPDATE
// locked between load and write so concurrent updates don't trample
// each other.
//
// Only the mutable fields (ip_hash, expires_at, refresh_until,
// last_used_at) are written back; everything else (id, identity, time
// of creation, revocation state) is immutable from this method's
// perspective.
//
// Returns ErrAuthSessionNotFound if the id doesn't exist,
// ErrAuthSessionRevoked if the row exists but has been revoked,
// update's error if it returns one (the row is not modified), or any
// tx/DB error.
func (p *Postgres) Update(
	ctx context.Context,
	id string,
	update func(domain.AuthSession) (domain.AuthSession, error),
) (domain.AuthSession, error) {
	ctx, span := p.tracer.Start(ctx, "Postgres.Update")
	defer span.End()

	if id == "" {
		return domain.AuthSession{}, domain.ErrAuthSessionNotFound
	}

	tx, err := p.db.BeginTxx(ctx, nil)
	if err != nil {
		err := fmt.Errorf("failed to begin tx: %w", err)
		reporting.Report(ctx, err)
		return domain.AuthSession{}, err
	}
	defer tx.Rollback()

	var row dbAuthSession
	err = tx.QueryRowxContext(
		ctx,
		fmt.Sprintf(`SELECT id, identity_type, identity_key, ip_hash,
			created_at, expires_at, refresh_until, lifetime_ends_at, last_used_at, revoked_at
			FROM %s.auth_sessions WHERE id = $1 FOR UPDATE`,
			pq.QuoteIdentifier(p.schema)),
		id,
	).StructScan(&row)
	if errors.Is(err, sql.ErrNoRows) {
		return domain.AuthSession{}, domain.ErrAuthSessionNotFound
	}
	if err != nil {
		err := fmt.Errorf("failed to load auth session for update: %w", err)
		reporting.Report(ctx, err)
		return domain.AuthSession{}, err
	}

	current, err := row.toDomain()
	if err != nil {
		err := fmt.Errorf("failed to decode loaded auth session: %w", err)
		reporting.Report(ctx, err)
		return domain.AuthSession{}, err
	}

	if current.RevokedAt != nil {
		return domain.AuthSession{}, domain.ErrAuthSessionRevoked
	}

	updated, err := update(current)
	if err != nil {
		return domain.AuthSession{}, fmt.Errorf("auth session update callback: %w", err)
	}

	_, err = tx.ExecContext(
		ctx,
		fmt.Sprintf(`UPDATE %s.auth_sessions
		SET ip_hash = $1, expires_at = $2, refresh_until = $3, last_used_at = $4
		WHERE id = $5`,
			pq.QuoteIdentifier(p.schema)),
		updated.IPHash,
		updated.ExpiresAt,
		updated.RefreshUntil,
		updated.LastUsedAt,
		id,
	)
	if err != nil {
		err := fmt.Errorf("failed to update auth session: %w", err)
		reporting.Report(ctx, err)
		return domain.AuthSession{}, err
	}

	if err := tx.Commit(); err != nil {
		err := fmt.Errorf("failed to commit auth session update: %w", err)
		reporting.Report(ctx, err)
		return domain.AuthSession{}, err
	}

	return updated, nil
}

// EnforceActiveIPCap soft-revokes sessions for a given
// (identity_type, ip_hash). Two things happen in a single UPDATE:
//   - any not-yet-revoked rows past their refresh_until get
//     revoked_reason = 'expired' and revoked_at = expires_at (the
//     session was provably unused after that point).
//   - if the number of still-active rows (revoked_at IS NULL AND
//     refresh_until > now) exceeds maxActive-1, the oldest excess
//     gets revoked_reason = 'evicted_by_ip_cap' and revoked_at = now
//     (the session is being actively killed now to make room).
//
// CASE expressions pick reason and timestamp at write time from each
// row's own refresh_until so each touched row gets the accurate "why"
// and "when." Idempotent: if there's nothing to revoke, this is a
// no-op.
func (p *Postgres) EnforceActiveIPCap(
	ctx context.Context,
	identityType domain.AuthSessionIdentityType,
	ipHash string,
	maxActive int,
	now time.Time,
) error {
	ctx, span := p.tracer.Start(ctx, "Postgres.EnforceActiveIPCap")
	defer span.End()

	if maxActive <= 0 {
		return nil
	}

	identityTypeDB, err := identityTypeToDB(identityType)
	if err != nil {
		err := fmt.Errorf("failed to encode identity type for ip cap: %w", err)
		reporting.Report(ctx, err)
		return err
	}

	_, err = p.db.ExecContext(
		ctx,
		fmt.Sprintf(`WITH targets AS (
			SELECT id FROM %s.auth_sessions
			WHERE identity_type = $1 AND ip_hash = $2
			  AND revoked_at IS NULL AND refresh_until <= $3
			UNION ALL
			(SELECT id FROM %s.auth_sessions
			 WHERE identity_type = $1 AND ip_hash = $2
			   AND revoked_at IS NULL AND refresh_until > $3
			 ORDER BY created_at DESC
			 OFFSET $4)
		)
		UPDATE %s.auth_sessions
		SET revoked_at = CASE WHEN refresh_until > $3 THEN $3 ELSE expires_at END,
		    revoked_reason = CASE WHEN refresh_until > $3 THEN $5 ELSE $6 END
		WHERE id IN (SELECT id FROM targets)`,
			pq.QuoteIdentifier(p.schema),
			pq.QuoteIdentifier(p.schema),
			pq.QuoteIdentifier(p.schema)),
		identityTypeDB,
		ipHash,
		now,
		maxActive-1,
		revokedReasonEvictedByIPCap,
		revokedReasonExpired,
	)
	if err != nil {
		err := fmt.Errorf("failed to enforce active ip cap: %w", err)
		reporting.Report(ctx, err)
		return err
	}
	return nil
}
