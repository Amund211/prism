package app

import (
	"context"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
)

type signInLister interface {
	ListActive(ctx context.Context, identityKey string, now time.Time) ([]domain.ActiveSignIn, error)
}

// ListMicrosoftSignIns returns the Microsoft sign-ins of a Microsoft-tier
// session's identity that have a live credential, for the active-sign-ins
// view.
// Any other tier gets domain.ErrAuthSessionTierRefused.
type ListMicrosoftSignIns func(ctx context.Context, identityType domain.AuthSessionIdentityType, identityKey string) ([]domain.ActiveSignIn, error)

func BuildListMicrosoftSignIns(credentials signInLister, nowFunc func() time.Time) ListMicrosoftSignIns {
	return func(ctx context.Context, identityType domain.AuthSessionIdentityType, identityKey string) ([]domain.ActiveSignIn, error) {
		if identityType != domain.AuthSessionIdentityMicrosoft {
			return nil, domain.ErrAuthSessionTierRefused
		}
		return credentials.ListActive(ctx, identityKey, nowFunc())
	}
}
