package app

import (
	"context"
	"net/http"
	"net/http/httptest"
	"sync"
	"testing"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type mockUserRepository struct {
	t *testing.T

	registerVisitUserID      string
	registerVisitCalled      bool
	registerVisitReturnUser  domain.User
	registerVisitReturnError error
}

func (m *mockUserRepository) RegisterVisit(ctx context.Context, userID string) (domain.User, error) {
	m.t.Helper()
	require.Equal(m.t, m.registerVisitUserID, userID)

	require.False(m.t, m.registerVisitCalled)

	m.registerVisitCalled = true
	return m.registerVisitReturnUser, m.registerVisitReturnError
}

func TestBuildRegisterUserVisit(t *testing.T) {
	t.Parallel()

	ctx := context.Background()
	now := time.Now()

	t.Run("success", func(t *testing.T) {
		t.Parallel()

		expectedUser := domain.User{
			UserID:      "test-user-123",
			FirstSeenAt: now,
			LastSeenAt:  now,
			SeenCount:   1,
		}

		repo := &mockUserRepository{
			t:                        t,
			registerVisitUserID:      "test-user-123",
			registerVisitReturnUser:  expectedUser,
			registerVisitReturnError: nil,
		}

		registerUserVisit := BuildRegisterUserVisit(repo)

		user, err := registerUserVisit(ctx, "test-user-123")
		require.NoError(t, err)
		require.Equal(t, expectedUser, user)
		require.True(t, repo.registerVisitCalled)
	})

	t.Run("repository error", func(t *testing.T) {
		t.Parallel()

		repo := &mockUserRepository{
			t:                        t,
			registerVisitUserID:      "test-user-456",
			registerVisitReturnUser:  domain.User{},
			registerVisitReturnError: assert.AnError,
		}

		registerUserVisit := BuildRegisterUserVisit(repo)

		user, err := registerUserVisit(ctx, "test-user-456")
		require.Error(t, err)
		require.ErrorIs(t, err, assert.AnError)
		require.Equal(t, domain.User{}, user)
		require.True(t, repo.registerVisitCalled)
	})
}

func TestBuildRegisterUserVisitMiddleware(t *testing.T) {
	t.Parallel()

	makeHandler := func() (http.HandlerFunc, *bool) {
		called := false
		return func(w http.ResponseWriter, r *http.Request) {
			called = true
			w.WriteHeader(http.StatusOK)
		}, &called
	}

	t.Run("next handler gets called properly", func(t *testing.T) {
		t.Parallel()

		registerUserVisit := func(ctx context.Context, userID string) (domain.User, error) {
			return domain.User{}, nil
		}
		middleware := BuildRegisterUserVisitMiddleware(registerUserVisit)

		t.Run("with user ID header", func(t *testing.T) {
			inner, innerCalled := makeHandler()

			handler := middleware(inner)

			req := httptest.NewRequest(http.MethodGet, "/test", nil)
			req.Header.Set("X-User-Id", "test-user")
			w := httptest.NewRecorder()

			handler(w, req)

			require.True(t, *innerCalled)
			require.Equal(t, http.StatusOK, w.Code)
		})

		t.Run("without user ID header", func(t *testing.T) {
			inner, innerCalled := makeHandler()

			handler := middleware(inner)

			req := httptest.NewRequest(http.MethodGet, "/test", nil)
			w := httptest.NewRecorder()

			handler(w, req)

			require.True(t, *innerCalled)
			require.Equal(t, http.StatusOK, w.Code)
		})

		t.Run("with strange user ID header", func(t *testing.T) {
			inner, innerCalled := makeHandler()

			handler := middleware(inner)

			req := httptest.NewRequest(http.MethodGet, "/test", nil)
			req.Header.Set("X-User-Id", "test-user;`DROP TABLES;--      sdlfkjsdlkfj  ---; ^&^%$#@!")
			w := httptest.NewRecorder()

			handler(w, req)

			require.True(t, *innerCalled)
			require.Equal(t, http.StatusOK, w.Code)
		})

		t.Run("if registerUserVisit errors", func(t *testing.T) {
			registerUserVisit := func(ctx context.Context, userID string) (domain.User, error) {
				return domain.User{}, assert.AnError
			}
			middleware := BuildRegisterUserVisitMiddleware(registerUserVisit)

			inner, innerCalled := makeHandler()

			handler := middleware(inner)

			req := httptest.NewRequest(http.MethodGet, "/test", nil)
			req.Header.Set("X-User-Id", "test-user")
			w := httptest.NewRecorder()

			handler(w, req)

			require.True(t, *innerCalled)
			require.Equal(t, http.StatusOK, w.Code)
		})
	})

	t.Run("registerUserVisit gets called with user ID from header", func(t *testing.T) {
		t.Parallel()

		var wg sync.WaitGroup
		wg.Add(1)

		var registeredUserID string
		registerUserVisit := func(ctx context.Context, userID string) (domain.User, error) {
			defer wg.Done()
			registeredUserID = userID
			return domain.User{}, nil
		}
		middleware := BuildRegisterUserVisitMiddleware(registerUserVisit)

		inner, _ := makeHandler()
		handler := middleware(inner)

		req := httptest.NewRequest(http.MethodGet, "/test", nil)
		req.Header.Set("X-User-Id", "test-user-123")
		w := httptest.NewRecorder()

		handler(w, req)

		wg.Wait()
		require.Equal(t, "test-user-123", registeredUserID)
	})

	t.Run("registerUserVisit gets called with <missing> when no user ID header", func(t *testing.T) {
		t.Parallel()

		var wg sync.WaitGroup
		wg.Add(1)

		var registeredUserID string
		registerUserVisit := func(ctx context.Context, userID string) (domain.User, error) {
			defer wg.Done()
			registeredUserID = userID
			return domain.User{}, nil
		}
		middleware := BuildRegisterUserVisitMiddleware(registerUserVisit)

		inner, _ := makeHandler()
		handler := middleware(inner)

		req := httptest.NewRequest(http.MethodGet, "/test", nil)
		w := httptest.NewRecorder()

		handler(w, req)

		wg.Wait()
		require.Equal(t, "<missing>", registeredUserID)
	})

	t.Run("registerUserVisit gets called with <missing> when user ID header is empty string", func(t *testing.T) {
		t.Parallel()

		var wg sync.WaitGroup
		wg.Add(1)

		var registeredUserID string
		registerUserVisit := func(ctx context.Context, userID string) (domain.User, error) {
			defer wg.Done()
			registeredUserID = userID
			return domain.User{}, nil
		}
		middleware := BuildRegisterUserVisitMiddleware(registerUserVisit)

		inner, _ := makeHandler()
		handler := middleware(inner)

		req := httptest.NewRequest(http.MethodGet, "/test", nil)
		req.Header.Set("X-User-Id", "")
		w := httptest.NewRecorder()

		handler(w, req)

		wg.Wait()
		require.Equal(t, "<missing>", registeredUserID)
	})
}
