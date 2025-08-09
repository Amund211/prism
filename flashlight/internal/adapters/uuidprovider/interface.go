package uuidprovider

import (
	"context"

	"github.com/Amund211/flashlight/internal/domain"
)

type UUIDProvider interface {
	// Returns the normalized UUID and authoritative username for the given username.
	//
	// Returns domain.ErrUsernameNotFound if the username does not exist.
	// Returns domain.ErrTemporarilyUnavailable if the provider implementation receives an error believed to be intermittent. The call may be retried later.
	GetAccountByUsername(ctx context.Context, username string) (domain.Account, error)
}
