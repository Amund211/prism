package userrepository

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

func newPostgres(t *testing.T, db *sqlx.DB, schemaSuffix string, nowFunc func() time.Time) (*Postgres, string) {
	require.NotEmpty(t, schemaSuffix, "schemaSuffix must not be empty")
	schema := fmt.Sprintf("users_repo_test_%s", schemaSuffix)

	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))

	db.MustExec(fmt.Sprintf("DROP SCHEMA IF EXISTS %s CASCADE", pq.QuoteIdentifier(schema)))

	migrator := database.NewDatabaseMigrator(db, logger)

	err := migrator.Migrate(t.Context(), schema)
	require.NoError(t, err)

	return NewPostgres(db, schema, nowFunc), schema
}

func TestPostgresRegisterVisit(t *testing.T) {
	if testing.Short() {
		t.Skip("skipping db tests in short mode.")
	}
	t.Parallel()

	getStoredUser := func(t *testing.T, db *sqlx.DB, schema string, userID string) *dbUser {
		t.Helper()

		ctx := t.Context()

		txx, err := db.Beginx()
		require.NoError(t, err)
		defer txx.Rollback()

		_, err = txx.ExecContext(ctx, fmt.Sprintf("SET search_path TO %s", pq.QuoteIdentifier(schema)))
		require.NoError(t, err)

		var user dbUser
		err = txx.QueryRowxContext(
			ctx,
			"SELECT user_id, first_seen_at, last_seen_at, seen_count FROM users WHERE user_id = $1",
			userID,
		).Scan(&user.UserID, &user.FirstSeenAt, &user.LastSeenAt, &user.SeenCount)
		if errors.Is(err, sql.ErrNoRows) {
			return nil
		}
		require.NoError(t, err)

		err = txx.Commit()
		require.NoError(t, err)

		return &user
	}

	requireEqualUsers := func(t *testing.T, expected, actual domain.User) {
		t.Helper()
		require.Equal(t, expected.UserID, actual.UserID)
		require.Equal(t, expected.SeenCount, actual.SeenCount)

		// Time can get truncated when round-tripping to the database
		require.WithinDuration(t, expected.FirstSeenAt, actual.FirstSeenAt, time.Millisecond)
		require.WithinDuration(t, expected.LastSeenAt, actual.LastSeenAt, time.Millisecond)
	}

	requireStoredUser := func(t *testing.T, db *sqlx.DB, schema string, expected domain.User) {
		t.Helper()
		stored := getStoredUser(t, db, schema, expected.UserID)
		require.NotNil(t, stored)
		requireEqualUsers(t, expected, domain.User{
			UserID:      stored.UserID,
			SeenCount:   stored.SeenCount,
			FirstSeenAt: stored.FirstSeenAt,
			LastSeenAt:  stored.LastSeenAt,
		})
	}

	t.Run("First visit creates new user", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()

		db, err := database.NewPostgresDatabase(database.LOCAL_CONNECTION_STRING)
		require.NoError(t, err)
		defer db.Close()

		currentTime := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
		nowFunc := func() time.Time {
			return currentTime
		}

		p, schema := newPostgres(t, db, "first_visit", nowFunc)
		userID := "test-user-1"

		user, err := p.RegisterVisit(ctx, userID)
		require.NoError(t, err)

		expectedUser := domain.User{
			UserID:      userID,
			SeenCount:   1,
			FirstSeenAt: currentTime,
			LastSeenAt:  currentTime,
		}

		requireEqualUsers(t, expectedUser, user)
		// First seen and last seen should be equal on first visit
		require.Equal(t, user.FirstSeenAt, user.LastSeenAt)

		// Verify in database
		requireStoredUser(t, db, schema, expectedUser)

		// First seen and last seen should be equal on first visit
		stored := getStoredUser(t, db, schema, userID)
		require.NotNil(t, stored)
		require.Equal(t, stored.FirstSeenAt, stored.LastSeenAt)
	})

	t.Run("Second visit updates last_seen_at and increments count", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()

		db, err := database.NewPostgresDatabase(database.LOCAL_CONNECTION_STRING)
		require.NoError(t, err)
		defer db.Close()

		currentTime := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
		nowFunc := func() time.Time {
			return currentTime
		}

		p, schema := newPostgres(t, db, "second_visit", nowFunc)
		userID := "test-user-2"

		firstExpected := domain.User{
			UserID:      userID,
			SeenCount:   1,
			FirstSeenAt: currentTime,
			LastSeenAt:  currentTime,
		}

		// First visit
		user1, err := p.RegisterVisit(ctx, userID)
		require.NoError(t, err)
		requireEqualUsers(t, firstExpected, user1)
		requireStoredUser(t, db, schema, firstExpected)

		// Advance time
		currentTime = currentTime.Add(1 * time.Minute)

		secondExpected := domain.User{
			UserID:      userID,
			SeenCount:   2,
			FirstSeenAt: firstExpected.FirstSeenAt,
			LastSeenAt:  currentTime,
		}

		// Second visit
		user2, err := p.RegisterVisit(ctx, userID)
		require.NoError(t, err)
		requireEqualUsers(t, secondExpected, user2)
		requireStoredUser(t, db, schema, secondExpected)

		require.Equal(t, user1.FirstSeenAt, user2.FirstSeenAt) // First seen should not change
	})

	t.Run("Multiple visits increment count correctly", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()

		db, err := database.NewPostgresDatabase(database.LOCAL_CONNECTION_STRING)
		require.NoError(t, err)
		defer db.Close()

		currentTime := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
		nowFunc := func() time.Time {
			return currentTime
		}

		p, schema := newPostgres(t, db, "multiple_visits", nowFunc)
		userID := "test-user-3"

		start := currentTime

		for i := range 5 {
			expected := domain.User{
				UserID:      userID,
				SeenCount:   int64(i + 1),
				FirstSeenAt: start,
				LastSeenAt:  currentTime,
			}

			user, err := p.RegisterVisit(ctx, userID)
			require.NoError(t, err)

			requireEqualUsers(t, expected, user)
			requireStoredUser(t, db, schema, expected)

			// Advance time
			currentTime = currentTime.Add(1 * time.Hour)
		}

		requireStoredUser(t, db, schema, domain.User{
			UserID:      userID,
			SeenCount:   5,
			FirstSeenAt: start,
			LastSeenAt:  start.Add(4 * time.Hour),
		})
	})

	t.Run("Different users are tracked independently", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()

		db, err := database.NewPostgresDatabase(database.LOCAL_CONNECTION_STRING)
		require.NoError(t, err)
		defer db.Close()

		currentTime := time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
		nowFunc := func() time.Time {
			return currentTime
		}

		p, schema := newPostgres(t, db, "multiple_users", nowFunc)
		user1ID := "test-user-4"
		user2ID := "test-user-5"

		t0 := currentTime

		// User 1 visits twice
		u1v1, err := p.RegisterVisit(ctx, user1ID)
		require.NoError(t, err)
		requireEqualUsers(t, domain.User{
			UserID:      user1ID,
			SeenCount:   1,
			FirstSeenAt: t0,
			LastSeenAt:  t0,
		}, u1v1)

		// Advance time
		currentTime = currentTime.Add(1 * time.Minute)
		t1 := currentTime

		u1v2, err := p.RegisterVisit(ctx, user1ID)
		require.NoError(t, err)
		requireEqualUsers(t, domain.User{
			UserID:      user1ID,
			SeenCount:   2,
			FirstSeenAt: t0,
			LastSeenAt:  t1,
		}, u1v2)

		// User 2 visits once
		u2v1, err := p.RegisterVisit(ctx, user2ID)
		require.NoError(t, err)
		requireEqualUsers(t, domain.User{
			UserID:      user2ID,
			SeenCount:   1,
			FirstSeenAt: t1,
			LastSeenAt:  t1,
		}, u2v1)

		// Verify both users in database
		requireStoredUser(t, db, schema, domain.User{
			UserID:      user1ID,
			SeenCount:   2,
			FirstSeenAt: t0,
			LastSeenAt:  t1,
		})
		requireStoredUser(t, db, schema, domain.User{
			UserID:      user2ID,
			SeenCount:   1,
			FirstSeenAt: t1,
			LastSeenAt:  t1,
		})
	})

	t.Run("Empty userID returns error", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()

		db, err := database.NewPostgresDatabase(database.LOCAL_CONNECTION_STRING)
		require.NoError(t, err)
		defer db.Close()

		nowFunc := func() time.Time {
			return time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
		}

		p, _ := newPostgres(t, db, "empty_userid", nowFunc)

		_, err = p.RegisterVisit(ctx, "")
		require.Error(t, err)
		require.Contains(t, err.Error(), "userID is empty")
	})

	t.Run("new user has no entry", func(t *testing.T) {
		t.Parallel()

		db, err := database.NewPostgresDatabase(database.LOCAL_CONNECTION_STRING)
		require.NoError(t, err)
		defer db.Close()

		nowFunc := func() time.Time {
			return time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
		}

		_, schema := newPostgres(t, db, "no_entry", nowFunc)

		stored := getStoredUser(t, db, schema, "nonexistent-user")
		require.Nil(t, stored)
	})

	t.Run("Special characters in userID are handled correctly", func(t *testing.T) {
		t.Parallel()
		ctx := t.Context()

		db, err := database.NewPostgresDatabase(database.LOCAL_CONNECTION_STRING)
		require.NoError(t, err)
		defer db.Close()

		nowFunc := func() time.Time {
			return time.Date(2024, 1, 1, 12, 0, 0, 0, time.UTC)
		}

		p, schema := newPostgres(t, db, "special_chars", nowFunc)
		userID := "user@`-'example.com; DROP TABLE users;--"

		user, err := p.RegisterVisit(ctx, userID)
		require.NoError(t, err)
		require.Equal(t, userID, user.UserID)
		require.Equal(t, int64(1), user.SeenCount)

		stored := getStoredUser(t, db, schema, userID)
		require.NotNil(t, stored)
		require.Equal(t, userID, stored.UserID)
	})
}
