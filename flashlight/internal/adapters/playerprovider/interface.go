package playerprovider

import (
	"context"

	"github.com/Amund211/flashlight/internal/domain"
)

type PlayerProvider interface {
	GetPlayer(ctx context.Context, uuid string) (*domain.PlayerPIT, error)
}
