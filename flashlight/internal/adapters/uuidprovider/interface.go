package uuidprovider

import (
	"context"
)

type Identity struct {
	Username string
	UUID     string
}

type UUIDProvider interface {
	// Returns the normalized UUID and authoritative username for the given username.
	//
	// Returns domain.ErrUsernameNotFound if the username does not exist.
	// Returns domain.ErrTemporarilyUnavailable if the provider implementation receives an error believed to be intermittent. The call may be retried later.
	GetUUID(ctx context.Context, username string) (Identity, error)
}
