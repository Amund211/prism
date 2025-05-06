package playerprovider

import (
	"context"

	"github.com/Amund211/flashlight/internal/domain"
)

type PlayerProvider interface {
	// Raises domain.ErrPlayerNotFound if no player data is found for the given UUID
	//
	// Raises domain.ErrTemporarilyUnavailable if the provider implementation receives an error believed to be intermittent. The call may be retried later.
	GetPlayer(ctx context.Context, uuid string) (*domain.PlayerPIT, error)
}
