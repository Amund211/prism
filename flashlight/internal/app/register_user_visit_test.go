package app

import (
	"context"
	"testing"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

type mockUserRepository struct {
	t *testing.T

	registerVisitUserID      string
	registerVisitIPHash      string
	registerVisitUserAgent   string
	registerVisitCalled      bool
	registerVisitReturnUser  domain.User
	registerVisitReturnError error
}

func (m *mockUserRepository) RegisterVisit(ctx context.Context, userID string, ipHash string, userAgent string) (domain.User, error) {
	m.t.Helper()
	require.Equal(m.t, m.registerVisitUserID, userID)
	require.Equal(m.t, m.registerVisitIPHash, ipHash)
	require.Equal(m.t, m.registerVisitUserAgent, userAgent)

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
			UserID:        "test-user-123",
			FirstSeenAt:   now,
			LastSeenAt:    now,
			SeenCount:     1,
			LastIPHash:    "test-ip-hash",
			LastUserAgent: "test-user-agent",
		}

		repo := &mockUserRepository{
			t:                        t,
			registerVisitUserID:      "test-user-123",
			registerVisitIPHash:      "test-ip-hash",
			registerVisitUserAgent:   "test-user-agent",
			registerVisitReturnUser:  expectedUser,
			registerVisitReturnError: nil,
		}

		registerUserVisit := BuildRegisterUserVisit(repo)

		user, err := registerUserVisit(ctx, "test-user-123", "test-ip-hash", "test-user-agent")
		require.NoError(t, err)
		require.Equal(t, expectedUser, user)
		require.True(t, repo.registerVisitCalled)
	})

	t.Run("repository error", func(t *testing.T) {
		t.Parallel()

		repo := &mockUserRepository{
			t:                        t,
			registerVisitUserID:      "test-user-456",
			registerVisitIPHash:      "test-ip-hash-456",
			registerVisitUserAgent:   "test-user-agent-456",
			registerVisitReturnUser:  domain.User{},
			registerVisitReturnError: assert.AnError,
		}

		registerUserVisit := BuildRegisterUserVisit(repo)

		user, err := registerUserVisit(ctx, "test-user-456", "test-ip-hash-456", "test-user-agent-456")
		require.Error(t, err)
		require.ErrorIs(t, err, assert.AnError)
		require.Equal(t, domain.User{}, user)
		require.True(t, repo.registerVisitCalled)
	})
}
