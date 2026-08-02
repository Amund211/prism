package authsessionrepository

import (
	"database/sql"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"sync"
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

	t.Run("Create leaves an identity's existing sessions active", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()

		db, err := database.NewPostgresDatabase(database.LocalConnectionString)
		require.NoError(t, err)
		defer db.Close()
		p, schema := newPostgres(t, db, "create_keeps_active")

		old := mkSession("flsess_old", "user-X")
		require.NoError(t, p.Create(ctx, old))

		// Second login for the same identity while the first is still
		// fresh. Nothing is revoked at issuance — the two coexist.
		fresh := mkSession("flsess_new", "user-X")
		fresh.CreatedAt = now.Add(10 * time.Minute)
		require.NoError(t, p.Create(ctx, fresh))

		for _, id := range []string{"flsess_old", "flsess_new"} {
			row := selectRow(t, db, schema, id)
			require.NotNil(t, row)
			require.False(t, row.RevokedAt.Valid,
				"%s should still be active: an identity may hold any number of concurrent sessions", id)
			require.False(t, row.RevokedReason.Valid)
		}
	})

	t.Run("Create leaves an identity's aged-out sessions untouched", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()

		db, err := database.NewPostgresDatabase(database.LocalConnectionString)
		require.NoError(t, err)
		defer db.Close()
		p, schema := newPostgres(t, db, "create_leaves_aged_out")

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

		// Create stamps nothing, so an aged-out row sits with revoked_at
		// NULL past its refresh_until. That is now the common case, not an
		// edge one: EnforceActiveIPCap is the only thing that ever stamps a
		// row, and it only runs on a later login from the same ip_hash. For
		// rows it never reaches, expires_at / lifetime_ends_at are the truth.
		oldRow := selectRow(t, db, schema, "flsess_old")
		require.NotNil(t, oldRow)
		require.False(t, oldRow.RevokedAt.Valid,
			"Create must not stamp an aged-out row — nothing revokes at issuance")
		require.False(t, oldRow.RevokedReason.Valid)
	})

	t.Run("Create admits concurrent issuance for one identity", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()

		db, err := database.NewPostgresDatabase(database.LocalConnectionString)
		require.NoError(t, err)
		defer db.Close()
		p, schema := newPostgres(t, db, "create_concurrent")

		// Concurrent logins for one identity are no longer a race to
		// serialize: with no unique index there is nothing for two inserts
		// to collide on, and two rows for one identity are simply two valid
		// sessions. Client-side single-flight remains worthwhile as an
		// optimisation, not for correctness.
		const concurrent = 8

		const identityKey = "user-concurrent"

		start := make(chan struct{})
		errs := make(chan error, concurrent)
		var wg sync.WaitGroup
		for i := range concurrent {
			wg.Add(1)
			go func() {
				defer wg.Done()
				sess := mkSession(fmt.Sprintf("flsess_concurrent-%d", i), identityKey)
				<-start
				errs <- p.Create(ctx, sess)
			}()
		}
		close(start)
		wg.Wait()
		close(errs)

		for err := range errs {
			require.NoError(t, err, "every concurrent login for one identity must succeed")
		}

		countWhere := func(predicate string) int {
			t.Helper()
			var count int
			require.NoError(t, db.GetContext(ctx, &count, fmt.Sprintf(
				`SELECT count(*) FROM %s.auth_sessions WHERE identity_key = $1 AND %s`,
				pq.QuoteIdentifier(schema), predicate,
			), identityKey))
			return count
		}

		require.Equal(t, concurrent, countWhere("TRUE"),
			"every caller should have inserted its row")
		require.Equal(t, concurrent, countWhere("revoked_at IS NULL"),
			"every session should be left active — issuance revokes nothing")
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
		// CreatedAt/LifetimeEndsAt are untouched by the callback, so they
		// come from the db read — must be normalized to UTC.
		require.Equal(t, time.UTC, updated.CreatedAt.Location())
		require.Equal(t, time.UTC, updated.LifetimeEndsAt.Location())

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
		// Soft-revoke it via the cap: a different identity logging in from
		// the same IP with a cap of 1 makes user-R the only over-cap victim.
		// EnforceActiveIPCap is the only thing that revokes anything now.
		require.NoError(t, p.EnforceActiveIPCap(ctx, domain.AuthSessionIdentityAnonymous, "user-S", "iphash-1", 1, now.Add(5*time.Minute)))

		_, err = p.Update(ctx, "flsess_old", func(s domain.AuthSession) (domain.AuthSession, error) {
			t.Fatal("update callback should not run on a revoked session")
			return s, nil
		})
		require.ErrorIs(t, err, domain.ErrAuthSessionRevoked)

		// Old row's revoked state should be untouched by the failed Update.
		row := selectRow(t, db, schema, "flsess_old")
		require.NotNil(t, row)
		require.Equal(t, revokedReasonEvictedByIPCap, row.RevokedReason.String)
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
		require.NoError(t, p.EnforceActiveIPCap(ctx, domain.AuthSessionIdentityAnonymous, "u-none", "ip-z", 2, callNow))

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

		require.NoError(t, p.EnforceActiveIPCap(ctx, domain.AuthSessionIdentityAnonymous, "u-none", "ip-y", 2, now))

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
		require.NoError(t, p.EnforceActiveIPCap(ctx, domain.AuthSessionIdentityAnonymous, "u-none", "ip-m", 2, callNow))

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

		mk := func(id, key string, createdAt time.Time) domain.AuthSession {
			s := mkSession(id, key)
			s.IPHash = "ip-r"
			s.CreatedAt = createdAt
			s.LastUsedAt = createdAt
			s.ExpiresAt = createdAt.Add(1 * time.Hour)
			s.RefreshUntil = createdAt.Add(2 * time.Hour)
			return s
		}
		require.NoError(t, p.Create(ctx, mk("flsess_v1", "u-r1", now)))
		require.NoError(t, p.Create(ctx, mk("flsess_v2", "u-r2", now.Add(1*time.Minute))))

		// cap=1 keeps no non-self identity, so both are evicted.
		evictedAt := now.Add(2 * time.Minute)
		require.NoError(t, p.EnforceActiveIPCap(ctx, domain.AuthSessionIdentityAnonymous, "u-none", "ip-r", 1, evictedAt))

		// A later under-cap call has nothing active to evict; the
		// already-revoked rows must not be re-stamped.
		require.NoError(t, p.EnforceActiveIPCap(ctx, domain.AuthSessionIdentityAnonymous, "u-none", "ip-r", 4, now.Add(3*time.Minute)))

		for _, id := range []string{"flsess_v1", "flsess_v2"} {
			row := selectRow(t, db, schema, id)
			require.NotNil(t, row)
			require.Equal(t, revokedReasonEvictedByIPCap, row.RevokedReason.String)
			require.True(t, row.RevokedAt.Time.Equal(evictedAt),
				"%s should keep its original revoked_at — already-revoked rows are skipped", id)
		}
	})

	// The outer UPDATE repeats `revoked_at IS NULL` even though both CTE arms
	// already filter on it. The CTEs are evaluated from the statement
	// snapshot while row locks are taken afterwards, so without the repeat
	// two logins from one IP racing on the same victim both stamp it and the
	// loser overwrites the winner's audit fields.
	t.Run("EnforceActiveIPCap does not overwrite a concurrent eviction", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()
		db, err := database.NewPostgresDatabase(database.LocalConnectionString)
		require.NoError(t, err)
		defer db.Close()
		p, schema := newPostgres(t, db, "evict_concurrent")

		victim := mkSession("flsess_race", "u-race-victim")
		victim.IPHash = "ip-race"
		require.NoError(t, p.Create(ctx, victim))

		// The two callers write deliberately different values, so the row
		// itself says which one wrote it last. The first evicts a row that is
		// still fresh; the second arrives past refresh_until, so it reaches
		// the same row through the expired-cleanup arm instead and would
		// stamp expires_at with a different reason.
		firstAt := now.Add(1 * time.Minute)
		secondAt := victim.RefreshUntil.Add(1 * time.Minute)

		// Hold the victim's row lock so both callers evaluate their CTEs
		// against a snapshot where it is still active, and only then queue
		// for the row. Postgres grants tuple locks in arrival order, so the
		// caller that queues first is the one that gets to stamp the row.
		blocker, err := db.Beginx()
		require.NoError(t, err)
		defer blocker.Rollback()
		var lockedID string
		require.NoError(t, blocker.QueryRowContext(ctx, fmt.Sprintf(
			`SELECT id FROM %s.auth_sessions WHERE id = $1 FOR UPDATE`,
			pq.QuoteIdentifier(schema),
		), victim.ID).Scan(&lockedID))

		// Scoped to this test's schema by the query text: the subtests in
		// this file run in parallel against the same table name.
		waitForLockWaiters := func(want int) {
			t.Helper()
			deadline := time.Now().Add(10 * time.Second)
			for {
				var waiting int
				require.NoError(t, db.GetContext(ctx, &waiting,
					`SELECT count(*) FROM pg_stat_activity
					WHERE wait_event_type = 'Lock' AND query LIKE $1`,
					"%"+schema+"%"))
				if waiting >= want {
					return
				}
				require.False(t, time.Now().After(deadline),
					"timed out waiting for %d blocked callers, saw %d", want, waiting)
				time.Sleep(10 * time.Millisecond)
			}
		}

		errs := make(chan error, 2)
		enforce := func(callerKey string, at time.Time) {
			errs <- p.EnforceActiveIPCap(ctx, domain.AuthSessionIdentityAnonymous, callerKey, "ip-race", 1, at)
		}
		go enforce("u-race-first", firstAt)
		waitForLockWaiters(1)
		go enforce("u-race-second", secondAt)
		waitForLockWaiters(2)

		require.NoError(t, blocker.Rollback())
		require.NoError(t, <-errs)
		require.NoError(t, <-errs)

		row := selectRow(t, db, schema, victim.ID)
		require.NotNil(t, row)
		require.Equal(t, revokedReasonEvictedByIPCap, row.RevokedReason.String,
			"the first caller's reason must survive — the second has to find the row already revoked")
		require.True(t, row.RevokedAt.Time.Equal(firstAt),
			"expected the first caller's %s, got %s: the loser overwrote the winner's audit fields",
			firstAt, row.RevokedAt.Time)
	})

	// The identity that's re-logging in occupies exactly one slot after the
	// login however many rows it holds, so it is already counted. Counting
	// it again would evict an unrelated identity for nothing.
	t.Run("EnforceActiveIPCap excludes the re-logging identity from the cap", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()
		db, err := database.NewPostgresDatabase(database.LocalConnectionString)
		require.NoError(t, err)
		defer db.Close()
		p, schema := newPostgres(t, db, "evict_skips_self")

		mk := func(id, key string, createdAt time.Time) domain.AuthSession {
			s := mkSession(id, key)
			s.IPHash = "ip-self"
			s.CreatedAt = createdAt
			s.LastUsedAt = createdAt
			s.ExpiresAt = createdAt.Add(1 * time.Hour)
			s.RefreshUntil = createdAt.Add(2 * time.Hour)
			return s
		}
		// D oldest .. A newest, all four active and at the cap.
		require.NoError(t, p.Create(ctx, mk("flsess_d", "u-d", now)))
		require.NoError(t, p.Create(ctx, mk("flsess_c", "u-c", now.Add(1*time.Minute))))
		require.NoError(t, p.Create(ctx, mk("flsess_b", "u-b", now.Add(2*time.Minute))))
		require.NoError(t, p.Create(ctx, mk("flsess_a", "u-a", now.Add(3*time.Minute))))

		// u-a re-logs in. Counting it as a fifth identity would push the
		// oldest (u-d) past OFFSET cap-1 and evict it.
		callNow := now.Add(4 * time.Minute)
		require.NoError(t, p.EnforceActiveIPCap(ctx, domain.AuthSessionIdentityAnonymous, "u-a", "ip-self", 4, callNow))

		for _, id := range []string{"flsess_a", "flsess_b", "flsess_c", "flsess_d"} {
			row := selectRow(t, db, schema, id)
			require.NotNil(t, row)
			require.False(t, row.RevokedAt.Valid,
				"%s should survive: the only identity over the cap is the one logging in, which is excluded", id)
		}
	})

	t.Run("EnforceActiveIPCap still evicts others when the re-logging identity is excluded", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()
		db, err := database.NewPostgresDatabase(database.LocalConnectionString)
		require.NoError(t, err)
		defer db.Close()
		p, schema := newPostgres(t, db, "evict_skips_self_still_evicts")

		mk := func(id, key string, createdAt time.Time) domain.AuthSession {
			s := mkSession(id, key)
			s.IPHash = "ip-self2"
			s.CreatedAt = createdAt
			s.LastUsedAt = createdAt
			s.ExpiresAt = createdAt.Add(1 * time.Hour)
			s.RefreshUntil = createdAt.Add(2 * time.Hour)
			return s
		}
		require.NoError(t, p.Create(ctx, mk("flsess_d", "u-d", now)))
		require.NoError(t, p.Create(ctx, mk("flsess_c", "u-c", now.Add(1*time.Minute))))
		require.NoError(t, p.Create(ctx, mk("flsess_b", "u-b", now.Add(2*time.Minute))))
		require.NoError(t, p.Create(ctx, mk("flsess_a", "u-a", now.Add(3*time.Minute))))

		// cap=2 keeps 1 non-self row active. Excluding u-a leaves b, c, d;
		// b is newest of those and survives, c and d go.
		callNow := now.Add(4 * time.Minute)
		require.NoError(t, p.EnforceActiveIPCap(ctx, domain.AuthSessionIdentityAnonymous, "u-a", "ip-self2", 2, callNow))

		for _, id := range []string{"flsess_c", "flsess_d"} {
			row := selectRow(t, db, schema, id)
			require.NotNil(t, row)
			require.True(t, row.RevokedAt.Valid, "%s is over the cap and should be evicted", id)
			require.Equal(t, revokedReasonEvictedByIPCap, row.RevokedReason.String)
		}
		bRow := selectRow(t, db, schema, "flsess_b")
		require.NotNil(t, bRow)
		require.False(t, bRow.RevokedAt.Valid, "newest non-self row stays active")
		aRow := selectRow(t, db, schema, "flsess_a")
		require.NotNil(t, aRow)
		require.False(t, aRow.RevokedAt.Valid,
			"the re-logging identity keeps its existing sessions — issuance revokes nothing")
	})

	// The exclusion is on the active branch only. An aged-out row for the
	// re-logging identity isn't competing for the cap either way, so it is
	// still stamped 'expired' — the audit trail should say why the row
	// actually died.
	t.Run("EnforceActiveIPCap still expires the re-logging identity's aged-out row", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()
		db, err := database.NewPostgresDatabase(database.LocalConnectionString)
		require.NoError(t, err)
		defer db.Close()
		p, schema := newPostgres(t, db, "expire_self")

		aged := mkSession("flsess_self_aged", "u-a")
		aged.IPHash = "ip-self3"
		aged.ExpiresAt = now.Add(-2 * time.Hour)
		aged.RefreshUntil = now.Add(-1 * time.Hour)
		require.NoError(t, p.Create(ctx, aged))

		// Well under the cap, so the only branch that can touch this row is
		// the expiry one.
		require.NoError(t, p.EnforceActiveIPCap(ctx, domain.AuthSessionIdentityAnonymous, "u-a", "ip-self3", 4, now))

		row := selectRow(t, db, schema, "flsess_self_aged")
		require.NotNil(t, row)
		require.True(t, row.RevokedAt.Valid,
			"an aged-out row is stamped even when it belongs to the identity logging in")
		require.Equal(t, revokedReasonExpired, row.RevokedReason.String)
		require.True(t, row.RevokedAt.Time.Equal(aged.ExpiresAt),
			"expired rows are stamped at expires_at, the last point the session was provably usable")
	})

	// The cap counts identities, not rows. If it counted rows, one user
	// reloading four times would fill a cap of 4 on their own and start
	// evicting strangers.
	t.Run("EnforceActiveIPCap counts identities, not rows", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()
		db, err := database.NewPostgresDatabase(database.LocalConnectionString)
		require.NoError(t, err)
		defer db.Close()
		p, schema := newPostgres(t, db, "cap_counts_identities")

		mk := func(id, key string, createdAt time.Time) domain.AuthSession {
			s := mkSession(id, key)
			s.IPHash = "ip-count"
			s.CreatedAt = createdAt
			s.LastUsedAt = createdAt
			s.ExpiresAt = createdAt.Add(1 * time.Hour)
			s.RefreshUntil = createdAt.Add(2 * time.Hour)
			return s
		}
		// One identity, four concurrent sessions — one occupied slot.
		ids := []string{"flsess_r1", "flsess_r2", "flsess_r3", "flsess_r4"}
		for i, id := range ids {
			require.NoError(t, p.Create(ctx, mk(id, "u-busy", now.Add(time.Duration(i)*time.Minute))))
		}

		// A second identity logs in against a cap of 2. u-busy is the only
		// other identity, so it fits and nothing is evicted.
		require.NoError(t, p.EnforceActiveIPCap(ctx, domain.AuthSessionIdentityAnonymous, "u-other", "ip-count", 2, now.Add(5*time.Minute)))

		for _, id := range ids {
			row := selectRow(t, db, schema, id)
			require.NotNil(t, row)
			require.False(t, row.RevokedAt.Valid,
				"%s should survive: four rows for one identity occupy one slot, not four", id)
		}
	})

	// Evicting only a victim's oldest row would free nothing — the victim
	// still holds the rest and still occupies a slot. So a chosen identity
	// is swept entirely, aged-out rows included.
	t.Run("EnforceActiveIPCap sweeps every row of a victim identity", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()
		db, err := database.NewPostgresDatabase(database.LocalConnectionString)
		require.NoError(t, err)
		defer db.Close()
		p, schema := newPostgres(t, db, "cap_sweeps_victim")

		mk := func(id, key string, createdAt, refreshUntil time.Time) domain.AuthSession {
			s := mkSession(id, key)
			s.IPHash = "ip-sweep"
			s.CreatedAt = createdAt
			s.LastUsedAt = createdAt
			s.ExpiresAt = refreshUntil.Add(-30 * time.Minute)
			s.RefreshUntil = refreshUntil
			return s
		}
		// Victim holds two active rows and one aged-out one.
		require.NoError(t, p.Create(ctx, mk("flsess_victim_a", "u-victim", now, now.Add(2*time.Hour))))
		require.NoError(t, p.Create(ctx, mk("flsess_victim_b", "u-victim", now.Add(1*time.Minute), now.Add(2*time.Hour))))
		aged := mk("flsess_victim_aged", "u-victim", now.Add(-3*time.Hour), now.Add(-1*time.Hour))
		require.NoError(t, p.Create(ctx, aged))
		// Survivor is newer, so the victim is the one over the cap.
		require.NoError(t, p.Create(ctx, mk("flsess_survivor", "u-survivor", now.Add(2*time.Minute), now.Add(2*time.Hour))))

		// cap=2 keeps 1 non-self identity: u-survivor stays, u-victim goes.
		callNow := now.Add(3 * time.Minute)
		require.NoError(t, p.EnforceActiveIPCap(ctx, domain.AuthSessionIdentityAnonymous, "u-new", "ip-sweep", 2, callNow))

		for _, id := range []string{"flsess_victim_a", "flsess_victim_b"} {
			row := selectRow(t, db, schema, id)
			require.NotNil(t, row)
			require.True(t, row.RevokedAt.Valid)
			require.Equal(t, revokedReasonEvictedByIPCap, row.RevokedReason.String,
				"%s: every active row of a victim identity closes, not just the oldest", id)
			require.True(t, row.RevokedAt.Time.Equal(callNow))
		}

		// The victim's aged-out row is swept in the same statement, but the
		// CASE gives it the reason it actually died of.
		agedRow := selectRow(t, db, schema, "flsess_victim_aged")
		require.NotNil(t, agedRow)
		require.True(t, agedRow.RevokedAt.Valid)
		require.Equal(t, revokedReasonExpired, agedRow.RevokedReason.String,
			"a victim's aged-out row is 'expired', not 'evicted_by_ip_cap'")
		require.True(t, agedRow.RevokedAt.Time.Equal(aged.ExpiresAt))

		survivor := selectRow(t, db, schema, "flsess_survivor")
		require.NotNil(t, survivor)
		require.False(t, survivor.RevokedAt.Valid, "the newest non-self identity stays")
	})

	// Identities are ranked by their newest session, so a stale identity
	// that logged in again recently is not the one evicted.
	t.Run("EnforceActiveIPCap ranks identities by their newest session", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()
		db, err := database.NewPostgresDatabase(database.LocalConnectionString)
		require.NoError(t, err)
		defer db.Close()
		p, schema := newPostgres(t, db, "cap_ranks_by_newest")

		mk := func(id, key string, createdAt time.Time) domain.AuthSession {
			s := mkSession(id, key)
			s.IPHash = "ip-rank"
			s.CreatedAt = createdAt
			s.LastUsedAt = createdAt
			s.ExpiresAt = createdAt.Add(1 * time.Hour)
			s.RefreshUntil = createdAt.Add(2 * time.Hour)
			return s
		}
		// u-old holds the oldest row of all, but also the newest.
		require.NoError(t, p.Create(ctx, mk("flsess_old_first", "u-old", now)))
		require.NoError(t, p.Create(ctx, mk("flsess_mid_only", "u-mid", now.Add(1*time.Minute))))
		require.NoError(t, p.Create(ctx, mk("flsess_old_latest", "u-old", now.Add(2*time.Minute))))

		// cap=2 keeps 1 non-self identity. Ranked by newest session u-old
		// wins, so u-mid is the victim — even though u-old owns the oldest
		// row on this IP.
		callNow := now.Add(3 * time.Minute)
		require.NoError(t, p.EnforceActiveIPCap(ctx, domain.AuthSessionIdentityAnonymous, "u-new", "ip-rank", 2, callNow))

		midRow := selectRow(t, db, schema, "flsess_mid_only")
		require.NotNil(t, midRow)
		require.True(t, midRow.RevokedAt.Valid, "u-mid's newest session is the older of the two")
		require.Equal(t, revokedReasonEvictedByIPCap, midRow.RevokedReason.String)

		for _, id := range []string{"flsess_old_first", "flsess_old_latest"} {
			row := selectRow(t, db, schema, id)
			require.NotNil(t, row)
			require.False(t, row.RevokedAt.Valid,
				"%s should survive: u-old is ranked by MAX(created_at), not its oldest row", id)
		}
	})

	t.Run("EnforceActiveIPCap no-op when under cap", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()
		db, err := database.NewPostgresDatabase(database.LocalConnectionString)
		require.NoError(t, err)
		defer db.Close()
		p, _ := newPostgres(t, db, "evict_under_cap")

		require.NoError(t, p.EnforceActiveIPCap(ctx, domain.AuthSessionIdentityAnonymous, "u-none", "no-ip", 4, now))
	})
}
