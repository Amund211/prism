package storage

import (
	"context"
	"time"

	"github.com/Amund211/flashlight/internal/processing"
)

type StatsPersistor interface {
	StoreStats(ctx context.Context, playerUUID string, player *processing.HypixelAPIPlayer, queriedAt time.Time) error
	GetHistory(ctx context.Context, playerUUID string, start, end time.Time, limit int) ([]PlayerDataPIT, error)
	GetSessions(ctx context.Context, playerUUID string, start, end time.Time) ([]Session, error)
}

type PlayerDataPIT struct {
	ID                string
	DataFormatVersion int
	UUID              string
	QueriedAt         time.Time
	Experience        *float64
	Solo              StatsPIT
	Doubles           StatsPIT
	Threes            StatsPIT
	Fours             StatsPIT
	Overall           StatsPIT
}

type StatsPIT struct {
	Winstreak   *int
	GamesPlayed *int
	Wins        *int
	Losses      *int
	BedsBroken  *int
	BedsLost    *int
	FinalKills  *int
	FinalDeaths *int
	Kills       *int
	Deaths      *int
}

type Session struct {
	Start PlayerDataPIT
	End   PlayerDataPIT
}
