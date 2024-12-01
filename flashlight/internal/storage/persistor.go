package storage

import (
	"context"
	"encoding/json"
	"fmt"
	"time"

	"github.com/Amund211/flashlight/internal/processing"
	"github.com/Amund211/flashlight/internal/strutils"
	"github.com/google/uuid"
	"github.com/jmoiron/sqlx"
	"github.com/lib/pq"
)

type StatsPersistor interface {
	StoreStats(ctx context.Context, playerUUID string, player *processing.HypixelAPIPlayer, queriedAt time.Time) error
}

type PostgresStatsPersistor struct {
	db     *sqlx.DB
	schema string
}

const MAIN_SCHEMA = "flashlight"
const TESTING_SCHEMA = "flashlight_test"

func GetSchemaName(isTesting bool) string {
	if isTesting {
		return TESTING_SCHEMA
	}
	return MAIN_SCHEMA
}

func NewPostgresStatsPersistor(db *sqlx.DB, schema string) *PostgresStatsPersistor {
	return &PostgresStatsPersistor{db, schema}
}

type playerDataStorage struct {
	Experience *float64         `json:"xp,omitempty"`
	Solo       statsDataStorage `json:"1"`
	Doubles    statsDataStorage `json:"2"`
	Threes     statsDataStorage `json:"3"`
	Fours      statsDataStorage `json:"4"`
	Overall    statsDataStorage `json:"all"`
}

type statsDataStorage struct {
	Winstreak   *int `json:"ws,omitempty"`
	Wins        *int `json:"w,omitempty"`
	Losses      *int `json:"l,omitempty"`
	BedsBroken  *int `json:"bb,omitempty"`
	BedsLost    *int `json:"bl,omitempty"`
	FinalKills  *int `json:"fk,omitempty"`
	FinalDeaths *int `json:"fd,omitempty"`
	Kills       *int `json:"k,omitempty"`
	Deaths      *int `json:"d,omitempty"`
}

func playerToDataStorage(player *processing.HypixelAPIPlayer) ([]byte, error) {
	if player == nil || player.Stats == nil || player.Stats.Bedwars == nil {
		return []byte(`{}`), nil
	}

	bw := player.Stats.Bedwars

	solo := statsDataStorage{
		Winstreak:   bw.SoloWinstreak,
		Wins:        bw.SoloWins,
		Losses:      bw.SoloLosses,
		BedsBroken:  bw.SoloBedsBroken,
		BedsLost:    bw.SoloBedsLost,
		FinalKills:  bw.SoloFinalKills,
		FinalDeaths: bw.SoloFinalDeaths,
		Kills:       bw.SoloKills,
		Deaths:      bw.SoloDeaths,
	}

	doubles := statsDataStorage{
		Winstreak:   bw.DoublesWinstreak,
		Wins:        bw.DoublesWins,
		Losses:      bw.DoublesLosses,
		BedsBroken:  bw.DoublesBedsBroken,
		BedsLost:    bw.DoublesBedsLost,
		FinalKills:  bw.DoublesFinalKills,
		FinalDeaths: bw.DoublesFinalDeaths,
		Kills:       bw.DoublesKills,
		Deaths:      bw.DoublesDeaths,
	}

	threes := statsDataStorage{
		Winstreak:   bw.ThreesWinstreak,
		Wins:        bw.ThreesWins,
		Losses:      bw.ThreesLosses,
		BedsBroken:  bw.ThreesBedsBroken,
		BedsLost:    bw.ThreesBedsLost,
		FinalKills:  bw.ThreesFinalKills,
		FinalDeaths: bw.ThreesFinalDeaths,
		Kills:       bw.ThreesKills,
		Deaths:      bw.ThreesDeaths,
	}

	fours := statsDataStorage{
		Winstreak:   bw.FoursWinstreak,
		Wins:        bw.FoursWins,
		Losses:      bw.FoursLosses,
		BedsBroken:  bw.FoursBedsBroken,
		BedsLost:    bw.FoursBedsLost,
		FinalKills:  bw.FoursFinalKills,
		FinalDeaths: bw.FoursFinalDeaths,
		Kills:       bw.FoursKills,
		Deaths:      bw.FoursDeaths,
	}

	overall := statsDataStorage{
		Winstreak:   bw.Winstreak,
		Wins:        bw.Wins,
		Losses:      bw.Losses,
		BedsBroken:  bw.BedsBroken,
		BedsLost:    bw.BedsLost,
		FinalKills:  bw.FinalKills,
		FinalDeaths: bw.FinalDeaths,
		Kills:       bw.Kills,
		Deaths:      bw.Deaths,
	}

	data := playerDataStorage{
		Experience: bw.Experience,
		Solo:       solo,
		Doubles:    doubles,
		Threes:     threes,
		Fours:      fours,
		Overall:    overall,
	}

	return json.Marshal(data)
}

func (p *PostgresStatsPersistor) StoreStats(ctx context.Context, playerUUID string, player *processing.HypixelAPIPlayer, queriedAt time.Time) error {
	if player == nil {
		return fmt.Errorf("StoreStats: player is nil")
	}

	normalizedUUID, err := strutils.NormalizeUUID(playerUUID)
	if err != nil {
		return fmt.Errorf("StoreStats: failed to normalize uuid: %w", err)
	}

	playerData, err := playerToDataStorage(player)
	if err != nil {
		return fmt.Errorf("StoreStats: failed to marshal player data: %w", err)
	}

	dbID, err := uuid.NewV7()
	if err != nil {
		return fmt.Errorf("StoreStats: failed to generate uuid: %w", err)
	}

	txx, err := p.db.BeginTxx(ctx, nil)
	if err != nil {
		return fmt.Errorf("StoreStats: failed to start transaction: %w", err)
	}
	defer txx.Rollback()

	_, err = txx.ExecContext(ctx, fmt.Sprintf("SET search_path TO %s", pq.QuoteIdentifier(p.schema)))
	if err != nil {
		return fmt.Errorf("StoreStats: failed to set search path: %w", err)
	}

	_, err = txx.Exec("INSERT INTO stats (id, player_uuid, player_data, queried_at) VALUES ($1, $2, $3, $4)", dbID.String(), normalizedUUID, playerData, queriedAt)
	if err != nil {
		return fmt.Errorf("StoreStats: failed to insert stats: %w", err)
	}

	err = txx.Commit()
	if err != nil {
		return fmt.Errorf("StoreStats: failed to commit transaction: %w", err)
	}
	return err
}

type StubPersistor struct{}

func (p *StubPersistor) StoreStats(ctx context.Context, playerUUID string, player *processing.HypixelAPIPlayer, queriedAt time.Time) error {
	return nil
}

func NewStubPersistor() *StubPersistor {
	return &StubPersistor{}
}
