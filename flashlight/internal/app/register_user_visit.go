package app

import (
	"context"
	"fmt"

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
