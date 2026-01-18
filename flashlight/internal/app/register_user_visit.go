package app

import (
	"context"
	"fmt"
	"net/http"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
)

type userRepository interface {
	RegisterVisit(ctx context.Context, userID string) (domain.User, error)
}

type RegisterUserVisit func(ctx context.Context, userID string) (domain.User, error)

func BuildRegisterUserVisit(repo userRepository) RegisterUserVisit {
	return func(ctx context.Context, userID string) (domain.User, error) {
		user, err := repo.RegisterVisit(ctx, userID)
		if err != nil {
			// NOTE: User repository handles its own error reporting
			return domain.User{}, fmt.Errorf("failed to register user visit in repository: %w", err)
		}
		return user, nil
	}
}

func BuildRegisterUserVisitMiddleware(registerUserVisit RegisterUserVisit) func(http.HandlerFunc) http.HandlerFunc {
	return func(next http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			go func() {
				// NOTE: Since we're doing this in a goroutine, we want a context
				//       that won't get cancelled when the request ends
				ctx, cancel := context.WithTimeout(
					context.WithoutCancel(r.Context()),
					1*time.Second,
				)
				defer cancel()

				userID := r.Header.Get("X-User-Id")
				if userID == "" {
					userID = "<missing>"
				}

				_, _ = registerUserVisit(ctx, userID)
			}()

			next(w, r)
		}
	}
}
