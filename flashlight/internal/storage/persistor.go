package storage

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"time"

	"github.com/Amund211/flashlight/internal/config"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/processing"
	"github.com/Amund211/flashlight/internal/strutils"
	"github.com/google/uuid"
	"github.com/jmoiron/sqlx"
	"github.com/lib/pq"
)

const DATA_FORMAT_VERSION = 1

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
	GamesPlayed *int `json:"gp,omitempty"`
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
		GamesPlayed: bw.SoloGamesPlayed,
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
		GamesPlayed: bw.DoublesGamesPlayed,
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
		GamesPlayed: bw.ThreesGamesPlayed,
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
		GamesPlayed: bw.FoursGamesPlayed,
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
		GamesPlayed: bw.GamesPlayed,
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

func statsPITFromDataStorage(data *statsDataStorage) *StatsPIT {
	return &StatsPIT{
		Winstreak:   data.Winstreak,
		GamesPlayed: data.GamesPlayed,
		Wins:        data.Wins,
		Losses:      data.Losses,
		BedsBroken:  data.BedsBroken,
		BedsLost:    data.BedsLost,
		FinalKills:  data.FinalKills,
		FinalDeaths: data.FinalDeaths,
		Kills:       data.Kills,
		Deaths:      data.Deaths,
	}
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

	var count int
	err = txx.QueryRowxContext(
		ctx,
		"SELECT COUNT(*) FROM stats WHERE player_uuid = $1 AND queried_at > $2",
		normalizedUUID,
		queriedAt.Add(-time.Minute),
	).Scan(&count)
	if err != nil {
		return fmt.Errorf("StoreStats: failed to query existing stats: %w", err)
	}
	if count > 0 {
		// Recent stats already exist, no need to store them again
		return nil
	}

	// Don't store consecutive duplicate stats
	var lastPlayerData []byte
	var lastDataFormatVersion int
	err = txx.QueryRowxContext(
		ctx,
		`SELECT
			data_format_version, player_data
		FROM stats
		WHERE
			player_uuid = $1 AND
			queried_at > $2
		ORDER BY queried_at DESC LIMIT 1`,
		normalizedUUID,
		queriedAt.Add(-1*time.Hour),
	).Scan(&lastDataFormatVersion, &lastPlayerData)
	if err == nil && lastDataFormatVersion == DATA_FORMAT_VERSION {
		equal, err := strutils.JSONStringsEqual(playerData, lastPlayerData)
		if err != nil {
			return fmt.Errorf("StoreStats: failed to compare player data: %w", err)
		}
		if equal {
			return nil
		}
	}
	if err != nil && !errors.Is(err, sql.ErrNoRows) {
		return fmt.Errorf("StoreStats: failed to query last player data: %w", err)
	}

	_, err = txx.ExecContext(
		ctx,
		`INSERT INTO stats
		(id, player_uuid, player_data, queried_at, data_format_version)
		VALUES ($1, $2, $3, $4, $5)`,
		dbID.String(),
		normalizedUUID,
		playerData,
		queriedAt,
		DATA_FORMAT_VERSION,
	)
	if err != nil {
		return fmt.Errorf("StoreStats: failed to insert stats: %w", err)
	}

	err = txx.Commit()
	if err != nil {
		return fmt.Errorf("StoreStats: failed to commit transaction: %w", err)
	}

	logging.FromContext(ctx).Info("Stored stats", "dataFormatVersion", DATA_FORMAT_VERSION)

	return nil
}

func (p *PostgresStatsPersistor) GetHistory(ctx context.Context, playerUUID string, start, end time.Time, limit int) ([]PlayerDataPIT, error) {
	if limit < 2 || limit > 1000 {
		// TODO: Use known error
		return nil, fmt.Errorf("GetHistory: invalid limit: %d", limit)
	}

	timespan := end.Sub(start)
	if timespan <= 0 {
		return nil, fmt.Errorf("GetHistory: end time must be after start time")
	}

	type dbStat struct {
		ID                string    `db:"id"`
		DataFormatVersion int       `db:"data_format_version"`
		UUID              string    `db:"player_uuid"`
		QueriedAt         time.Time `db:"queried_at"`
		PlayerData        []byte    `db:"player_data"`
	}

	dbStats := make([]dbStat, 0, limit)

	txx, err := p.db.BeginTxx(ctx, nil)
	if err != nil {
		return nil, fmt.Errorf("GetHistory: failed to start transaction: %w", err)
	}
	defer txx.Rollback()

	_, err = txx.ExecContext(ctx, fmt.Sprintf("SET search_path TO %s", pq.QuoteIdentifier(p.schema)))
	if err != nil {
		return nil, fmt.Errorf("StoreStats: failed to set search path: %w", err)
	}

	intervalLength := timespan / time.Duration(limit-1)
	for offset := 0; offset < limit-1; offset++ {
		intervalStart := start.Add(intervalLength * time.Duration(offset))
		intervalEnd := start.Add(intervalLength * time.Duration(offset+1))

		var stats []dbStat
		err = txx.SelectContext(
			ctx,
			&stats,
			`select
				id, data_format_version, player_uuid, queried_at, player_data
			from stats
			where
				player_uuid = $1 and
				queried_at >= $2 and
				queried_at < $3
			order by queried_at asc
			limit 1`,
			playerUUID, intervalStart, intervalEnd)
		if err != nil {
			return nil, fmt.Errorf("GetHistory: failed to select: %w", err)
		}
		if len(stats) > 1 {
			return nil, fmt.Errorf("GetHistory: expected at most one result, got %d", len(stats))
		}

		if len(stats) == 1 {
			dbStats = append(dbStats, stats[0])
		}
	}

	var stats []dbStat
	err = txx.SelectContext(
		ctx,
		&stats,
		`select
			id, data_format_version, player_uuid, queried_at, player_data
		from stats
		where
			player_uuid = $1 and
			queried_at >= $2 and
			queried_at <= $3
		order by queried_at desc
		limit 1`,
		playerUUID, end.Add(-1*intervalLength), end)
	if err != nil {
		return nil, fmt.Errorf("GetHistory: failed to select: %w", err)
	}
	if len(stats) > 1 {
		return nil, fmt.Errorf("GetHistory: expected at most one result, got %d", len(stats))
	}
	if len(stats) == 1 {
		dbStats = append(dbStats, stats[0])
	}

	err = txx.Commit()
	if err != nil {
		return nil, fmt.Errorf("StoreStats: failed to commit transaction: %w", err)
	}

	result := make([]PlayerDataPIT, 0, len(dbStats))
	for _, dbStat := range dbStats {
		var playerData playerDataStorage
		err := json.Unmarshal(dbStat.PlayerData, &playerData)
		if err != nil {
			return nil, fmt.Errorf("GetHistory: failed to unmarshal player data: %w", err)
		}
		result = append(result, PlayerDataPIT{
			ID:                dbStat.ID,
			DataFormatVersion: dbStat.DataFormatVersion,
			UUID:              dbStat.UUID,
			QueriedAt:         dbStat.QueriedAt,
			Experience:        playerData.Experience,
			Solo:              *statsPITFromDataStorage(&playerData.Solo),
			Doubles:           *statsPITFromDataStorage(&playerData.Doubles),
			Threes:            *statsPITFromDataStorage(&playerData.Threes),
			Fours:             *statsPITFromDataStorage(&playerData.Fours),
			Overall:           *statsPITFromDataStorage(&playerData.Overall),
		})
	}

	return result, nil
}

type StubPersistor struct{}

func (p *StubPersistor) StoreStats(ctx context.Context, playerUUID string, player *processing.HypixelAPIPlayer, queriedAt time.Time) error {
	return nil
}

func (p *StubPersistor) GetHistory(ctx context.Context, playerUUID string, start, end time.Time, limit int) ([]PlayerDataPIT, error) {
	return []PlayerDataPIT{}, nil
}

func NewStubPersistor() *StubPersistor {
	return &StubPersistor{}
}

func NewPostgresStatsPersistorOrMock(conf config.Config, logger *slog.Logger) (StatsPersistor, error) {
	var connectionString string
	if conf.IsDevelopment() {
		connectionString = LOCAL_CONNECTION_STRING
	} else {
		connectionString = GetCloudSQLConnectionString(conf.DBUsername(), conf.DBPassword(), conf.CloudSQLUnixSocketPath())
	}

	persistorSchemaName := GetSchemaName(!conf.IsProduction())

	logger.Info("Initializing database connection")
	db, err := NewPostgresDatabase(connectionString)

	if err == nil {
		NewDatabaseMigrator(db, logger.With("component", "migrator")).Migrate(persistorSchemaName)
		return NewPostgresStatsPersistor(db, persistorSchemaName), nil
	}

	if conf.IsDevelopment() {
		logger.Warn("Failed to connect to database. Falling back to stub persistor.", "errror", err.Error())
		return NewStubPersistor(), nil
	}

	return nil, fmt.Errorf("Failed to connect to database: %w", err)
}
