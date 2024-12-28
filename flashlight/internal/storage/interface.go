package storage

import (
	"context"
	"time"

	"github.com/Amund211/flashlight/internal/processing"
)

type StatsPersistor interface {
	StoreStats(ctx context.Context, playerUUID string, player *processing.HypixelAPIPlayer, queriedAt time.Time) error
}
