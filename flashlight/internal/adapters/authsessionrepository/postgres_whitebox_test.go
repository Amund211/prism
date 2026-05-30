package authsessionrepository

import (
	"database/sql"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"testing"
	"time"

	"github.com/jmoiron/sqlx"
	"github.com/lib/pq"
	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/adapters/database"
	"github.com/Amund211/flashlight/internal/domain"
)

func newPostgres(t *testing.T, db *sqlx.DB, schemaSuffix string) (*Postgres, string) {
	require.NotEmpty(t, schemaSuffix)
	schema := fmt.Sprintf("auth_sessions_repo_test_%s", schemaSuffix)

	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	db.MustExec(fmt.Sprintf("DROP SCHEMA IF EXISTS %s CASCADE", pq.QuoteIdentifier(schema)))

	migrator := database.NewDatabaseMigrator(db, logger)
	err := migrator.Migrate(t.Context(), schema)
	require.NoError(t, err)

	return NewPostgres(db, schema), schema
}

// testAuthSessionRow is a test-local projection that also pulls
// revoked_reason out of the DB so we can assert on the audit field.
// Production code doesn't expose it on the domain type, but tests
// want to verify it.
type testAuthSessionRow struct {
	ID             string         `db:"id"`
	IdentityType   string         `db:"identity_type"`
	IdentityKey    string         `db:"identity_key"`
	IPHash         string         `db:"ip_hash"`
	CreatedAt      time.Time      `db:"created_at"`
	ExpiresAt      time.Time      `db:"expires_at"`
	RefreshUntil   time.Time      `db:"refresh_until"`
	LifetimeEndsAt time.Time      `db:"lifetime_ends_at"`
	LastUsedAt     time.Time      `db:"last_used_at"`
	RevokedAt      sql.NullTime   `db:"revoked_at"`
	RevokedReason  sql.NullString `db:"revoked_reason"`
}

func selectRow(t *testing.T, db *sqlx.DB, schema string, id string) *testAuthSessionRow {
	t.Helper()
	ctx := t.Context()

	txx, err := db.Beginx()
	require.NoError(t, err)
	defer txx.Rollback()

	_, err = txx.ExecContext(ctx, fmt.Sprintf("SET search_path TO %s", pq.QuoteIdentifier(schema)))
	require.NoError(t, err)

	var row testAuthSessionRow
	err = txx.QueryRowxContext(
		ctx,
		`SELECT id, identity_type, identity_key, ip_hash, created_at, expires_at,
			refresh_until, lifetime_ends_at, last_used_at, revoked_at, revoked_reason
			FROM auth_sessions WHERE id = $1`,
		id,
	).StructScan(&row)
	if errors.Is(err, sql.ErrNoRows) {
		return nil
	}
	require.NoError(t, err)
	return &row
}

func TestPostgresAuthSession(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping db tests in short mode.")
	}
	t.Parallel()

	now := time.Date(2026, 5, 30, 10, 0, 0, 0, time.UTC)

	mkSession := func(id, key string) domain.AuthSession {
		return domain.AuthSession{
			ID:             id,
			IdentityType:   domain.AuthSessionIdentityAnonymous,
			IdentityKey:    key,
			IPHash:         "iphash-1",
			CreatedAt:      now,
			ExpiresAt:      now.Add(1 * time.Hour),
			RefreshUntil:   now.Add(2 * time.Hour),
			LifetimeEndsAt: now.Add(24 * time.Hour),
			LastUsedAt:     now,
		}
	}

	t.Run("Create persists the session with revoked_at NULL", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()

		db, err := database.NewPostgresDatabase(database.LocalConnectionString)
		require.NoError(t, err)
		defer db.Close()
		p, schema := newPostgres(t, db, "create")

		sess := mkSession("flsess_create-1", "user-A")
		require.NoError(t, p.Create(ctx, sess))

		row := selectRow(t, db, schema, "flsess_create-1")
		require.NotNil(t, row)
		require.False(t, row.RevokedAt.Valid, "fresh row should have NULL revoked_at")
		require.False(t, row.RevokedReason.Valid)
		require.True(t, row.LifetimeEndsAt.Equal(sess.LifetimeEndsAt),
			"lifetime_ends_at should be persisted from the caller-supplied value")
	})

	t.Run("Create soft-revokes an active replacement as 'replaced'", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()

		db, err := database.NewPostgresDatabase(database.LocalConnectionString)
		require.NoError(t, err)
		defer db.Close()
		p, schema := newPostgres(t, db, "create_replaces_active")

		old := mkSession("flsess_old", "user-X")
		require.NoError(t, p.Create(ctx, old))

		// New session created while the old one is still fresh.
		fresh := mkSession("flsess_new", "user-X")
		fresh.CreatedAt = now.Add(10 * time.Minute)
		require.NoError(t, p.Create(ctx, fresh))

		oldRow := selectRow(t, db, schema, "flsess_old")
		require.NotNil(t, oldRow, "old row should still exist for audit")
		require.True(t, oldRow.RevokedAt.Valid)
		require.True(t, oldRow.RevokedReason.Valid)
		require.Equal(t, revokedReasonReplaced, oldRow.RevokedReason.String)
		require.True(t, oldRow.RevokedAt.Time.Equal(fresh.CreatedAt),
			"replaced reaps actively kill the session at the new session's CreatedAt, "+
				"so revoked_at == that timestamp (not refresh_until)")

		newRow := selectRow(t, db, schema, "flsess_new")
		require.NotNil(t, newRow)
		require.False(t, newRow.RevokedAt.Valid)
	})

	t.Run("Create soft-revokes an aged-out replacement as 'expired'", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()

		db, err := database.NewPostgresDatabase(database.LocalConnectionString)
		require.NoError(t, err)
		defer db.Close()
		p, schema := newPostgres(t, db, "create_replaces_expired")

		// Old session: expires in 20min, refresh window ends 30min in.
		old := mkSession("flsess_old", "user-Y")
		old.CreatedAt = now
		old.ExpiresAt = now.Add(20 * time.Minute)
		old.RefreshUntil = now.Add(30 * time.Minute)
		require.NoError(t, p.Create(ctx, old))

		// New session created an hour later — past the old refresh window.
		fresh := mkSession("flsess_new", "user-Y")
		fresh.CreatedAt = now.Add(1 * time.Hour)
		fresh.ExpiresAt = fresh.CreatedAt.Add(1 * time.Hour)
		fresh.RefreshUntil = fresh.CreatedAt.Add(2 * time.Hour)
		require.NoError(t, p.Create(ctx, fresh))

		oldRow := selectRow(t, db, schema, "flsess_old")
		require.NotNil(t, oldRow)
		require.True(t, oldRow.RevokedAt.Valid)
		require.Equal(t, revokedReasonExpired, oldRow.RevokedReason.String)
		require.True(t, oldRow.RevokedAt.Time.Equal(oldRow.ExpiresAt),
			"expired reaps stamp revoked_at = expires_at — the last point the "+
				"session was provably usable; anything past that is dead time")
	})

	t.Run("Update applies fn and persists the result", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()
		db, err := database.NewPostgresDatabase(database.LocalConnectionString)
		require.NoError(t, err)
		defer db.Close()
		p, schema := newPostgres(t, db, "update_apply")

		original := mkSession("flsess_u", "user-U")
		require.NoError(t, p.Create(ctx, original))

		bumped := now.Add(30 * time.Minute)
		// Try to mutate lifetime_ends_at via the callback to verify
		// Update doesn't write it.
		tamperedLifetime := original.LifetimeEndsAt.Add(48 * time.Hour)
		updated, err := p.Update(ctx, "flsess_u", func(s domain.AuthSession) (domain.AuthSession, error) {
			s.ExpiresAt = bumped.Add(1 * time.Hour)
			s.RefreshUntil = bumped.Add(2 * time.Hour)
			s.IPHash = "iphash-new"
			s.LastUsedAt = bumped
			s.LifetimeEndsAt = tamperedLifetime
			return s, nil
		})
		require.NoError(t, err)
		require.WithinDuration(t, bumped.Add(1*time.Hour), updated.ExpiresAt, time.Millisecond)
		require.Equal(t, "iphash-new", updated.IPHash)

		row := selectRow(t, db, schema, "flsess_u")
		require.NotNil(t, row)
		require.Equal(t, "iphash-new", row.IPHash)
		require.True(t, row.LifetimeEndsAt.Equal(original.LifetimeEndsAt),
			"Update must not write lifetime_ends_at, even if the callback returns a different value")
	})

	t.Run("Update propagates fn errors without writing", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()
		db, err := database.NewPostgresDatabase(database.LocalConnectionString)
		require.NoError(t, err)
		defer db.Close()
		p, schema := newPostgres(t, db, "update_fn_err")

		require.NoError(t, p.Create(ctx, mkSession("flsess_e", "user-E")))

		_, err = p.Update(ctx, "flsess_e", func(s domain.AuthSession) (domain.AuthSession, error) {
			return domain.AuthSession{}, domain.ErrAuthSessionRefreshExpired
		})
		require.ErrorIs(t, err, domain.ErrAuthSessionRefreshExpired)

		row := selectRow(t, db, schema, "flsess_e")
		require.NotNil(t, row, "session should still exist")
		require.Equal(t, "iphash-1", row.IPHash, "row should not have been modified")
	})

	t.Run("Update on missing id returns NotFound", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()
		db, err := database.NewPostgresDatabase(database.LocalConnectionString)
		require.NoError(t, err)
		defer db.Close()
		p, _ := newPostgres(t, db, "update_missing")

		_, err = p.Update(ctx, "flsess_no-such", func(s domain.AuthSession) (domain.AuthSession, error) {
			t.Fatal("fn should not be called for missing id")
			return s, nil
		})
		require.ErrorIs(t, err, domain.ErrAuthSessionNotFound)
	})

	t.Run("Update on revoked id returns ErrAuthSessionRevoked", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()
		db, err := database.NewPostgresDatabase(database.LocalConnectionString)
		require.NoError(t, err)
		defer db.Close()
		p, schema := newPostgres(t, db, "update_revoked")

		require.NoError(t, p.Create(ctx, mkSession("flsess_old", "user-R")))
		// Trigger soft-revoke via Create-replaces.
		later := mkSession("flsess_new", "user-R")
		later.CreatedAt = now.Add(5 * time.Minute)
		require.NoError(t, p.Create(ctx, later))

		_, err = p.Update(ctx, "flsess_old", func(s domain.AuthSession) (domain.AuthSession, error) {
			t.Fatal("update callback should not run on a revoked session")
			return s, nil
		})
		require.ErrorIs(t, err, domain.ErrAuthSessionRevoked)

		// Old row's revoked state should be untouched by the failed Update.
		row := selectRow(t, db, schema, "flsess_old")
		require.NotNil(t, row)
		require.Equal(t, revokedReasonReplaced, row.RevokedReason.String)
	})

	t.Run("EnforceActiveIPCap soft-revokes excess oldest with 'evicted_by_ip_cap'", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()
		db, err := database.NewPostgresDatabase(database.LocalConnectionString)
		require.NoError(t, err)
		defer db.Close()
		p, schema := newPostgres(t, db, "evict_excess")

		mk := func(id, key string, createdAt time.Time) domain.AuthSession {
			s := mkSession(id, key)
			s.IPHash = "ip-z"
			s.CreatedAt = createdAt
			s.LastUsedAt = createdAt
			s.ExpiresAt = createdAt.Add(1 * time.Hour)
			s.RefreshUntil = createdAt.Add(2 * time.Hour)
			return s
		}
		require.NoError(t, p.Create(ctx, mk("flsess_old", "u-old", now)))
		require.NoError(t, p.Create(ctx, mk("flsess_mid", "u-mid", now.Add(1*time.Minute))))
		require.NoError(t, p.Create(ctx, mk("flsess_new", "u-new", now.Add(2*time.Minute))))

		// cap=2 means keep at most 1 active so a new insert lands within cap.
		callNow := now.Add(3 * time.Minute)
		require.NoError(t, p.EnforceActiveIPCap(ctx, domain.AuthSessionIdentityAnonymous, "ip-z", 2, callNow))

		oldRow := selectRow(t, db, schema, "flsess_old")
		require.NotNil(t, oldRow, "evicted rows should still exist for audit")
		require.True(t, oldRow.RevokedAt.Valid)
		require.Equal(t, revokedReasonEvictedByIPCap, oldRow.RevokedReason.String)
		require.True(t, oldRow.RevokedAt.Time.Equal(callNow),
			"actively-evicted rows are killed now, so revoked_at == call's now")

		midRow := selectRow(t, db, schema, "flsess_mid")
		require.NotNil(t, midRow)
		require.True(t, midRow.RevokedAt.Valid)
		require.Equal(t, revokedReasonEvictedByIPCap, midRow.RevokedReason.String)
		require.True(t, midRow.RevokedAt.Time.Equal(callNow))

		newRow := selectRow(t, db, schema, "flsess_new")
		require.NotNil(t, newRow)
		require.False(t, newRow.RevokedAt.Valid, "newest should remain active")
	})

	t.Run("EnforceActiveIPCap marks expired sessions as 'expired'", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()
		db, err := database.NewPostgresDatabase(database.LocalConnectionString)
		require.NoError(t, err)
		defer db.Close()
		p, schema := newPostgres(t, db, "evict_marks_expired")

		mk := func(id, key string, refreshUntil time.Time) domain.AuthSession {
			s := mkSession(id, key)
			s.IPHash = "ip-y"
			// Keep expires_at strictly before refresh_until so the row
			// shape is realistic for both expired and active cases.
			s.ExpiresAt = refreshUntil.Add(-30 * time.Minute)
			s.RefreshUntil = refreshUntil
			return s
		}
		require.NoError(t, p.Create(ctx, mk("flsess_expired", "u-e", now.Add(-1*time.Hour))))
		require.NoError(t, p.Create(ctx, mk("flsess_active", "u-a", now.Add(1*time.Hour))))

		require.NoError(t, p.EnforceActiveIPCap(ctx, domain.AuthSessionIdentityAnonymous, "ip-y", 2, now))

		expiredRow := selectRow(t, db, schema, "flsess_expired")
		require.NotNil(t, expiredRow)
		require.True(t, expiredRow.RevokedAt.Valid,
			"aged-out session should now be revoked")
		require.Equal(t, revokedReasonExpired, expiredRow.RevokedReason.String)
		require.True(t, expiredRow.RevokedAt.Time.Equal(expiredRow.ExpiresAt),
			"expired reaps stamp revoked_at = expires_at, not the call's now")

		activeRow := selectRow(t, db, schema, "flsess_active")
		require.NotNil(t, activeRow)
		require.False(t, activeRow.RevokedAt.Valid,
			"still-active session under cap should be untouched")
	})

	t.Run("EnforceActiveIPCap mixes 'evicted_by_ip_cap' and 'expired' in one call", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()
		db, err := database.NewPostgresDatabase(database.LocalConnectionString)
		require.NoError(t, err)
		defer db.Close()
		p, schema := newPostgres(t, db, "evict_mixed_reasons")

		mk := func(id, key string, createdAt, refreshUntil time.Time) domain.AuthSession {
			s := mkSession(id, key)
			s.IPHash = "ip-m"
			s.CreatedAt = createdAt
			s.LastUsedAt = createdAt
			s.ExpiresAt = refreshUntil.Add(-30 * time.Minute)
			s.RefreshUntil = refreshUntil
			return s
		}
		// Two active sessions and one expired one, same IP.
		require.NoError(t, p.Create(ctx, mk("flsess_active_old", "u-1", now, now.Add(2*time.Hour))))
		require.NoError(t, p.Create(ctx, mk("flsess_active_new", "u-2", now.Add(1*time.Minute), now.Add(2*time.Hour))))
		require.NoError(t, p.Create(ctx, mk("flsess_aged", "u-3", now.Add(-3*time.Hour), now.Add(-1*time.Hour))))

		// cap=2 → keep at most 1 active so the over-cap active gets
		// 'evicted_by_ip_cap' and the aged one gets 'expired'.
		callNow := now.Add(2 * time.Minute)
		require.NoError(t, p.EnforceActiveIPCap(ctx, domain.AuthSessionIdentityAnonymous, "ip-m", 2, callNow))

		oldActive := selectRow(t, db, schema, "flsess_active_old")
		require.NotNil(t, oldActive)
		require.True(t, oldActive.RevokedAt.Valid)
		require.Equal(t, revokedReasonEvictedByIPCap, oldActive.RevokedReason.String,
			"still-active over-cap session should be 'evicted_by_ip_cap'")
		require.True(t, oldActive.RevokedAt.Time.Equal(callNow),
			"evicted-while-active rows are killed now, so revoked_at == call's now")

		aged := selectRow(t, db, schema, "flsess_aged")
		require.NotNil(t, aged)
		require.True(t, aged.RevokedAt.Valid)
		require.Equal(t, revokedReasonExpired, aged.RevokedReason.String,
			"aged-out session should be 'expired'")
		require.True(t, aged.RevokedAt.Time.Equal(aged.ExpiresAt),
			"expired-and-reaped rows stamp revoked_at = expires_at, even when reaped alongside an active eviction")

		newActive := selectRow(t, db, schema, "flsess_active_new")
		require.NotNil(t, newActive)
		require.False(t, newActive.RevokedAt.Valid,
			"newest active under cap should be untouched")
	})

	t.Run("EnforceActiveIPCap ignores already-revoked sessions", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()
		db, err := database.NewPostgresDatabase(database.LocalConnectionString)
		require.NoError(t, err)
		defer db.Close()
		p, schema := newPostgres(t, db, "evict_skips_revoked")

		// Three sessions for the same ip+identity_key; Create chain
		// will soft-revoke earlier ones as 'replaced'.
		mk := func(id string, createdAt time.Time) domain.AuthSession {
			s := mkSession(id, "u-r")
			s.IPHash = "ip-r"
			s.CreatedAt = createdAt
			s.LastUsedAt = createdAt
			s.ExpiresAt = createdAt.Add(1 * time.Hour)
			s.RefreshUntil = createdAt.Add(2 * time.Hour)
			return s
		}
		require.NoError(t, p.Create(ctx, mk("flsess_v1", now)))
		require.NoError(t, p.Create(ctx, mk("flsess_v2", now.Add(1*time.Minute))))
		require.NoError(t, p.Create(ctx, mk("flsess_v3", now.Add(2*time.Minute))))

		// At this point: v1 and v2 are revoked ('replaced'), v3 active.
		// cap=4 → no eviction needed; check that already-revoked rows
		// aren't disturbed.
		require.NoError(t, p.EnforceActiveIPCap(ctx, domain.AuthSessionIdentityAnonymous, "ip-r", 4, now.Add(3*time.Minute)))

		v1 := selectRow(t, db, schema, "flsess_v1")
		require.NotNil(t, v1)
		require.Equal(t, revokedReasonReplaced, v1.RevokedReason.String,
			"reason should remain 'replaced', not overwritten by EnforceActiveIPCap")
	})

	t.Run("EnforceActiveIPCap no-op when under cap", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()
		db, err := database.NewPostgresDatabase(database.LocalConnectionString)
		require.NoError(t, err)
		defer db.Close()
		p, _ := newPostgres(t, db, "evict_under_cap")

		require.NoError(t, p.EnforceActiveIPCap(ctx, domain.AuthSessionIdentityAnonymous, "no-ip", 4, now))
	})
}
