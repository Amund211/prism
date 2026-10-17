package ports

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/domain"
)

func TestAuthLabel(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, 8, 8, 12, 0, 0, 0, time.UTC)

	validateAs := func(identityType domain.AuthSessionIdentityType, err error) func(context.Context, string) (domain.AuthSession, error) {
		return func(ctx context.Context, sessionID string) (domain.AuthSession, error) {
			return domain.AuthSession{
				ID:           sessionID,
				IdentityType: identityType,
				IdentityKey:  "user-xyz",
				ExpiresAt:    now.Add(time.Hour),
			}, err
		}
	}

	cases := []struct {
		name          string
		authorization string
		validate      func(context.Context, string) (domain.AuthSession, error)
		blocklist     BlocklistConfig
		want          authType
	}{
		{
			name:     "no Authorization header",
			validate: validateAs("", errors.New("not called")),
			want:     authTypeMissing,
		},
		{
			name:          "anonymous session",
			authorization: "Bearer good-token",
			validate:      validateAs(domain.AuthSessionIdentityAnonymous, nil),
			want:          authTypeAnonymous,
		},
		{
			name:          "microsoft session",
			authorization: "Bearer good-token",
			validate:      validateAs(domain.AuthSessionIdentityMicrosoft, nil),
			want:          authTypeMicrosoft,
		},
		{
			name:          "unknown identity type",
			authorization: "Bearer good-token",
			validate:      validateAs("some-future-tier", nil),
			want:          authTypeUnknown,
		},
		{
			name:          "blocked identity keeps its tier",
			authorization: "Bearer good-token",
			validate:      validateAs(domain.AuthSessionIdentityMicrosoft, nil),
			blocklist:     BlocklistConfig{UserIDs: []string{"user-xyz"}},
			want:          authTypeMicrosoft,
		},
		{
			name:          "malformed header",
			authorization: "Basic creds",
			validate:      validateAs("", errors.New("not called")),
			want:          authTypeInvalid,
		},
		{
			name:          "unknown session",
			authorization: "Bearer dead-token",
			validate:      validateAs("", domain.ErrAuthSessionNotFound),
			want:          authTypeInvalid,
		},
		{
			name:          "revoked session",
			authorization: "Bearer dead-token",
			validate:      validateAs("", domain.ErrAuthSessionRevoked),
			want:          authTypeInvalid,
		},
		{
			name:          "expired session",
			authorization: "Bearer dead-token",
			validate:      validateAs("", domain.ErrAuthSessionExpired),
			want:          authTypeInvalid,
		},
		{
			name:          "validate fails unexpectedly",
			authorization: "Bearer good-token",
			validate:      validateAs("", errors.New("the database is on fire")),
			want:          authTypeError,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			mw := NewBearerAuthMiddleware(tc.validate, func() time.Time { return now }, tc.blocklist)
			handler := mw(func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(http.StatusOK)
			})

			ctx, label := withAuthLabel(t.Context())
			r := httptest.NewRequestWithContext(ctx, http.MethodGet, "/v1/playerdata", http.NoBody)
			if tc.authorization != "" {
				r.Header.Set("Authorization", tc.authorization)
			}
			handler(httptest.NewRecorder(), r)

			require.Equal(t, tc.want, label.value)
		})
	}

	t.Run("defaults to not-checked when the bearer middleware does not run", func(t *testing.T) {
		t.Parallel()
		_, label := withAuthLabel(t.Context())
		require.Equal(t, authTypeNotChecked, label.value)
	})

	t.Run("setting without a holder is a no-op", func(t *testing.T) {
		t.Parallel()
		setAuthLabel(t.Context(), authTypeAnonymous)
	})
}
