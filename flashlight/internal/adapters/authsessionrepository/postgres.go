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
// Both are written by EnforceActiveIPCap, which is the only thing that
// ever stamps a row.
const (
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
		t := r.RevokedAt.Time.UTC()
		revokedAt = &t
	}
	return domain.AuthSession{
		ID:             r.ID,
		IdentityType:   identityType,
		IdentityKey:    r.IdentityKey,
		IPHash:         r.IPHash,
		CreatedAt:      r.CreatedAt.UTC(),
		ExpiresAt:      r.ExpiresAt.UTC(),
		RefreshUntil:   r.RefreshUntil.UTC(),
		LifetimeEndsAt: r.LifetimeEndsAt.UTC(),
		LastUsedAt:     r.LastUsedAt.UTC(),
		RevokedAt:      revokedAt,
	}, nil
}

// Create inserts a complete session into the table. The caller is
// responsible for filling in every field, including a unique ID and a
// last_used_at value (typically set to created_at on initial issue).
//
// An identity may hold any number of concurrent active sessions.
// Nothing is revoked at issuance: duplicates coexist and expire
// naturally, so two concurrent Creates for one identity are simply two
// valid sessions. Concurrent logins are still wasteful — two rows where
// one would do — so client-side single-flight is worth keeping, as an
// optimisation rather than for correctness.
//
// The invariant that makes this safe: rate limiting keys on the
// identity, never on the session id. N sessions must never mean N
// budgets, or a caller could mint unlimited quota by logging in
// repeatedly.
func (p *Postgres) Create(ctx context.Context, sess domain.AuthSession) error {
	ctx, span := p.tracer.Start(ctx, "Postgres.Create")
	defer span.End()

	identityTypeDB, err := identityTypeToDB(sess.IdentityType)
	if err != nil {
		err := fmt.Errorf("failed to encode identity type for create: %w", err)
		reporting.Report(ctx, err)
		return err
	}

	_, err = p.db.ExecContext(
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
//   - if the number of *identities* holding still-active rows
//     (revoked_at IS NULL AND refresh_until > now) exceeds
//     maxActive-1, the excess identities are evicted: every one of
//     their rows gets revoked_at = now and revoked_reason =
//     'evicted_by_ip_cap' (the sessions are being actively killed now
//     to make room).
//
// Identities are ranked by MAX(created_at) — the identity whose most
// recent *login* is oldest is evicted first. That is deliberately not
// the same as least-recently-*used*: last_used_at is the better notion
// of staleness, but it is only bumped once per validate-cache window,
// so it is noisier than it looks, while created_at is exact and
// monotone. The cost is that a long-lived session refreshed in place
// keeps its original created_at, so a continuously-used session can be
// evicted ahead of newer idle ones. Unsettled; see the auth working
// doc.
//
// The cap counts identities, not rows, because an identity may hold any
// number of concurrent sessions. Counting rows would let one user
// reloading four times fill a cap of 4 alone, and evicting a victim's
// oldest row would free nothing — the victim still holds the rest and
// still occupies a slot. Rows are bounded by the login limiter instead.
//
// identityKey is the identity that's about to log in. It is excluded
// from the eviction candidates and from the count they're measured
// against, because it is already counted: it occupies exactly one slot
// after the login regardless of how many rows it holds. That makes
// OFFSET maxActive-1 correct whether or not it already has an active
// session here, so no conditional is needed. Only the active branch
// excludes it: an aged-out row for the same identity is still worth
// stamping 'expired' for the audit trail, and it isn't competing for
// the cap either way.
//
// The eviction arm deliberately does not filter on refresh_until —
// once an identity is chosen, all its rows close, aged-out ones getting
// 'expired' from the CASE, which is the accurate reason anyway. UNION
// ALL can therefore list a row twice; `id IN (…)` makes that a no-op.
//
// CASE expressions pick reason and timestamp at write time from each
// row's own refresh_until so each touched row gets the accurate "why"
// and "when." Idempotent: if there's nothing to revoke, this is a
// no-op.
//
// The outer UPDATE repeats revoked_at IS NULL even though both CTE arms
// already filter on it. The CTEs are evaluated from the statement
// snapshot while the row locks are taken afterwards, so two logins from
// one IP racing on the same victim would otherwise both stamp it and
// the loser would overwrite the winner's revoked_at/reason. Repeating
// the predicate on the UPDATE puts it in the concurrent re-check, which
// runs against the updated row version. Audit data only, but free.
func (p *Postgres) EnforceActiveIPCap(
	ctx context.Context,
	identityType domain.AuthSessionIdentityType,
	identityKey string,
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
		fmt.Sprintf(`WITH victims AS (
			SELECT identity_key FROM (
				SELECT identity_key, MAX(created_at) AS newest
				FROM %s.auth_sessions
				WHERE identity_type = $1 AND ip_hash = $2
				  AND revoked_at IS NULL AND refresh_until > $3
				  AND identity_key <> $7
				GROUP BY identity_key
				ORDER BY newest DESC
				OFFSET $4
			) over_cap
		),
		targets AS (
			SELECT id FROM %s.auth_sessions
			WHERE identity_type = $1 AND ip_hash = $2
			  AND revoked_at IS NULL AND refresh_until <= $3
			UNION ALL
			SELECT id FROM %s.auth_sessions
			WHERE identity_type = $1 AND ip_hash = $2 AND revoked_at IS NULL
			  AND identity_key IN (SELECT identity_key FROM victims)
		)
		UPDATE %s.auth_sessions
		SET revoked_at = CASE WHEN refresh_until > $3 THEN $3 ELSE expires_at END,
		    revoked_reason = CASE WHEN refresh_until > $3 THEN $5 ELSE $6 END
		WHERE id IN (SELECT id FROM targets) AND revoked_at IS NULL`,
			pq.QuoteIdentifier(p.schema),
			pq.QuoteIdentifier(p.schema),
			pq.QuoteIdentifier(p.schema),
			pq.QuoteIdentifier(p.schema)),
		identityTypeDB,
		ipHash,
		now,
		maxActive-1,
		revokedReasonEvictedByIPCap,
		revokedReasonExpired,
		identityKey,
	)
	if err != nil {
		err := fmt.Errorf("failed to enforce active ip cap: %w", err)
		reporting.Report(ctx, err)
		return err
	}
	return nil
}
