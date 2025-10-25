package ports

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/Amund211/flashlight/internal/reporting"
)

type accountResponse struct {
	Success  bool   `json:"success"`
	Username string `json:"username,omitempty"`
	UUID     string `json:"uuid,omitempty"`
	Cause    string `json:"cause,omitempty"`
}

func MakeGetAccountByUsernameHandler(
	getAccountByUsername app.GetAccountByUsername,
	allowedOrigins *DomainSuffixes,
	rootLogger *slog.Logger,
	sentryMiddleware func(http.HandlerFunc) http.HandlerFunc,
) http.HandlerFunc {
	ipLimiter, _ := ratelimiting.NewTokenBucketRateLimiter(
		ratelimiting.RefillPerSecond(8),
		ratelimiting.BurstSize(480),
	)
	ipRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
		ipLimiter,
		ratelimiting.IPKeyFunc,
	)
	userIDLimiter, _ := ratelimiting.NewTokenBucketRateLimiter(
		ratelimiting.RefillPerSecond(2),
		ratelimiting.BurstSize(120),
	)
	userIDRateLimiter := ratelimiting.NewRequestBasedRateLimiter(
		// NOTE: Rate limiting based on user controlled value
		userIDLimiter,
		ratelimiting.UserIDKeyFunc,
	)

	makeOnLimitExceeded := func(rateLimiter ratelimiting.RequestRateLimiter) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusTooManyRequests)
			w.Write([]byte(`{"success":false,"cause":"rate limit exceeded"}`))
		}
	}

	middleware := ComposeMiddlewares(
		buildMetricsMiddleware(),
		logging.NewRequestLoggerMiddleware(rootLogger),
		sentryMiddleware,
		reporting.NewAddMetaMiddleware("get_account_by_username"),
		BuildCORSMiddleware(allowedOrigins),
		NewRateLimitMiddleware(ipRateLimiter, makeOnLimitExceeded(ipRateLimiter)),
		NewRateLimitMiddleware(userIDRateLimiter, makeOnLimitExceeded(userIDRateLimiter)),
	)

	handler := func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()
		username := r.PathValue("username")

		handleError := func(ctx context.Context, cause string, statusCode int) {
			response, err := makeErrorAccountResponseForUsername(ctx, username, cause)
			if err != nil {
				reporting.Report(ctx, fmt.Errorf("failed to marshal error response: %w", err))
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusInternalServerError)
				w.Write([]byte(`{"success":false,"cause":"internal server error"}`))
				return
			}

			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(statusCode)
			w.Write(response)
		}

		userID := r.Header.Get("X-User-Id")
		ctx = reporting.SetUserIDInContext(ctx, userID)
		if userID == "" {
			userID = "<missing>"
		}
		ctx = logging.AddMetaToContext(ctx,
			slog.String("userId", userID),
			slog.String("username", username),
		)
		ctx = reporting.AddExtrasToContext(ctx,
			map[string]string{
				"username": username,
			},
		)

		usernameLength := len(username)
		if usernameLength == 0 || usernameLength > 100 {
			username = "<invalid>"
			handleError(ctx, "invalid username length", http.StatusBadRequest)
			return
		}

		account, err := getAccountByUsername(ctx, username)
		if errors.Is(err, domain.ErrUsernameNotFound) {
			handleError(ctx, "not found", http.StatusNotFound)
			return
		} else if errors.Is(err, domain.ErrTemporarilyUnavailable) {
			handleError(ctx, "temporarily unavailable", http.StatusServiceUnavailable)
			return
		}

		if err != nil {
			// NOTE: GetAccountByUsername implementations handle their own error reporting
			handleError(ctx, "internal server error", http.StatusInternalServerError)
			return
		}

		ctx = reporting.AddExtrasToContext(ctx,
			map[string]string{
				"uuid": account.UUID,
			},
		)
		ctx = logging.AddMetaToContext(ctx, slog.String("uuid", account.UUID))

		response, err := makeSuccessAccountResponse(ctx, account)
		if err != nil {
			reporting.Report(ctx, fmt.Errorf("failed to create success response: %w", err))
			handleError(ctx, "internal server error", http.StatusInternalServerError)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		w.Write(response)
	}

	return middleware(handler)
}

func makeAccountResponse(ctx context.Context, username string, success bool, uuid string, cause string) ([]byte, error) {
	resp := accountResponse{
		Success:  success,
		Username: username,
		UUID:     uuid,
		Cause:    cause,
	}
	data, err := json.Marshal(resp)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal response: %w", err)
	}
	return data, nil
}

func makeSuccessAccountResponse(ctx context.Context, account domain.Account) ([]byte, error) {
	return makeAccountResponse(ctx, account.Username, true, account.UUID, "")
}

func makeErrorAccountResponseForUsername(ctx context.Context, username string, cause string) ([]byte, error) {
	return makeAccountResponse(ctx, username, false, "", cause)
}
