package playerrepository

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"slices"
	"strconv"
	"time"

	"github.com/Amund211/flashlight/internal/config"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/reporting"
	"github.com/Amund211/flashlight/internal/strutils"
	"github.com/google/uuid"
	"github.com/jmoiron/sqlx"
	"github.com/lib/pq"
)

const DATA_FORMAT_VERSION = 1

type PostgresPlayerRepository struct {
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

func NewPostgresPlayerRepository(db *sqlx.DB, schema string) *PostgresPlayerRepository {
	return &PostgresPlayerRepository{db, schema}
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
	GamesPlayed int  `json:"gp,omitempty"`
	Wins        int  `json:"w,omitempty"`
	Losses      int  `json:"l,omitempty"`
	BedsBroken  int  `json:"bb,omitempty"`
	BedsLost    int  `json:"bl,omitempty"`
	FinalKills  int  `json:"fk,omitempty"`
	FinalDeaths int  `json:"fd,omitempty"`
	Kills       int  `json:"k,omitempty"`
	Deaths      int  `json:"d,omitempty"`
}

type dbStat struct {
	ID                string    `db:"id"`
	DataFormatVersion int       `db:"data_format_version"`
	UUID              string    `db:"player_uuid"`
	QueriedAt         time.Time `db:"queried_at"`
	PlayerData        []byte    `db:"player_data"`
}

type playerPITWithID struct {
	domain.PlayerPIT
	ID string
}

func gamemodeStatsToDataStorage(stats *domain.GamemodeStatsPIT) statsDataStorage {
	return statsDataStorage{
		Winstreak:   stats.Winstreak,
		GamesPlayed: stats.GamesPlayed,
		Wins:        stats.Wins,
		Losses:      stats.Losses,
		BedsBroken:  stats.BedsBroken,
		BedsLost:    stats.BedsLost,
		FinalKills:  stats.FinalKills,
		FinalDeaths: stats.FinalDeaths,
		Kills:       stats.Kills,
		Deaths:      stats.Deaths,
	}
}

func playerToDataStorage(player *domain.PlayerPIT) ([]byte, error) {
	if player == nil {
		return []byte(`{}`), nil
	}

	var experience *float64
	if player.Experience != 500 {
		experience = &player.Experience
	}

	data := playerDataStorage{
		Experience: experience,
		Solo:       gamemodeStatsToDataStorage(&player.Solo),
		Doubles:    gamemodeStatsToDataStorage(&player.Doubles),
		Threes:     gamemodeStatsToDataStorage(&player.Threes),
		Fours:      gamemodeStatsToDataStorage(&player.Fours),
		Overall:    gamemodeStatsToDataStorage(&player.Overall),
	}

	json, err := json.Marshal(data)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal playerdatastorage: %w", err)
	}
	return json, nil
}

func gamemodeStatsPITFromDataStorage(data *statsDataStorage) *domain.GamemodeStatsPIT {
	return &domain.GamemodeStatsPIT{
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

func dbStatToPlayerPITWithID(dbStat dbStat) (*playerPITWithID, error) {
	var playerData playerDataStorage
	err := json.Unmarshal(dbStat.PlayerData, &playerData)
	if err != nil {
		return nil, fmt.Errorf("failed to unmarshal player data: %w", err)
	}

	experience := 500.0
	if playerData.Experience != nil {
		experience = *playerData.Experience
	}

	playerPIT := domain.PlayerPIT{
		QueriedAt: dbStat.QueriedAt,

		UUID: dbStat.UUID,

		// NOTE: Not currently stored to postgres
		Displayname: nil,
		LastLogin:   nil,
		LastLogout:  nil,

		Experience: experience,
		Solo:       *gamemodeStatsPITFromDataStorage(&playerData.Solo),
		Doubles:    *gamemodeStatsPITFromDataStorage(&playerData.Doubles),
		Threes:     *gamemodeStatsPITFromDataStorage(&playerData.Threes),
		Fours:      *gamemodeStatsPITFromDataStorage(&playerData.Fours),
		Overall:    *gamemodeStatsPITFromDataStorage(&playerData.Overall),
	}

	return &playerPITWithID{
		ID:        dbStat.ID,
		PlayerPIT: playerPIT,
	}, nil
}

func (p *PostgresPlayerRepository) StorePlayer(ctx context.Context, player *domain.PlayerPIT) error {
	if player == nil {
		err := fmt.Errorf("player is nil")
		reporting.Report(ctx, err)
		return err
	}

	if !strutils.UUIDIsNormalized(player.UUID) {
		err := fmt.Errorf("uuid is not normalized")
		reporting.Report(ctx, err, map[string]string{
			"uuid": player.UUID,
		})
		return err
	}

	playerData, err := playerToDataStorage(player)
	if err != nil {
		err := fmt.Errorf("failed to convert player to data storage: %w", err)
		reporting.Report(ctx, err, map[string]string{
			"uuid": player.UUID,
		})
		return err
	}

	dbID, err := uuid.NewV7()
	if err != nil {
		err := fmt.Errorf("failed to generate db id: %w", err)
		reporting.Report(ctx, err, map[string]string{
			"uuid": player.UUID,
		})
		return err
	}

	txx, err := p.db.BeginTxx(ctx, nil)
	if err != nil {
		err := fmt.Errorf("failed to start transaction: %w", err)
		reporting.Report(ctx, err, map[string]string{
			"uuid": player.UUID,
		})
		return err
	}
	defer txx.Rollback()

	_, err = txx.ExecContext(ctx, fmt.Sprintf("SET search_path TO %s", pq.QuoteIdentifier(p.schema)))
	if err != nil {
		err := fmt.Errorf("failed to set search path: %w", err)
		reporting.Report(ctx, err, map[string]string{
			"uuid": player.UUID,
		})
		return err
	}

	var count int
	err = txx.QueryRowxContext(
		ctx,
		"SELECT COUNT(*) FROM stats WHERE player_uuid = $1 AND queried_at > $2",
		player.UUID,
		player.QueriedAt.Add(-time.Minute),
	).Scan(&count)
	if err != nil {
		err := fmt.Errorf("failed to query recent entries: %w", err)
		reporting.Report(ctx, err, map[string]string{
			"uuid": player.UUID,
		})
		return err
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
		player.UUID,
		player.QueriedAt.Add(-1*time.Hour),
	).Scan(&lastDataFormatVersion, &lastPlayerData)
	if err == nil {
		if lastDataFormatVersion == DATA_FORMAT_VERSION {
			// Found recent stats with the same data format version -> compare
			equal, err := strutils.JSONStringsEqual(playerData, lastPlayerData)
			if err != nil {
				err := fmt.Errorf("failed to compare player data to previously stored data: %w", err)
				reporting.Report(ctx, err, map[string]string{
					"uuid": player.UUID,
				})
				return err
			}
			if equal {
				// Recent stats were equal -> don't store
				return nil
			}
		}
	} else if errors.Is(err, sql.ErrNoRows) {
		// No recent stats -> store
	} else {
		err := fmt.Errorf("failed to query last player data: %w", err)
		reporting.Report(ctx, err, map[string]string{
			"uuid": player.UUID,
		})
		return err
	}

	_, err = txx.ExecContext(
		ctx,
		`INSERT INTO stats
		(id, player_uuid, player_data, queried_at, data_format_version)
		VALUES ($1, $2, $3, $4, $5)`,
		dbID.String(),
		player.UUID,
		playerData,
		player.QueriedAt,
		DATA_FORMAT_VERSION,
	)
	if err != nil {
		err := fmt.Errorf("failed to insert new stats: %w", err)
		reporting.Report(ctx, err, map[string]string{
			"uuid": player.UUID,
		})
		return err
	}

	err = txx.Commit()
	if err != nil {
		err := fmt.Errorf("failed to commit transaction: %w", err)
		reporting.Report(ctx, err, map[string]string{
			"uuid": player.UUID,
		})
		return err
	}

	logging.FromContext(ctx).Info("Stored stats", "dataFormatVersion", DATA_FORMAT_VERSION)

	return nil
}

func (p *PostgresPlayerRepository) GetHistory(ctx context.Context, playerUUID string, start, end time.Time, limit int) ([]domain.PlayerPIT, error) {
	if limit < 2 || limit > 1000 {
		// TODO: Use known error
		err := fmt.Errorf("invalid limit")
		reporting.Report(ctx, err, map[string]string{
			"uuid":  playerUUID,
			"start": start.Format(time.RFC3339),
			"end":   end.Format(time.RFC3339),
			"limit": strconv.Itoa(limit),
		})
		return nil, err
	}

	timespan := end.Sub(start)
	if timespan <= 0 {
		err := fmt.Errorf("end time must be after start time")
		reporting.Report(ctx, err, map[string]string{
			"uuid":     playerUUID,
			"start":    start.Format(time.RFC3339),
			"end":      end.Format(time.RFC3339),
			"limit":    strconv.Itoa(limit),
			"timespan": timespan.String(),
		})
		return nil, err
	}

	dbStats := make([]dbStat, 0, limit)

	txx, err := p.db.BeginTxx(ctx, nil)
	if err != nil {
		err := fmt.Errorf("failed to start transaction: %w", err)
		reporting.Report(ctx, err, map[string]string{
			"uuid":  playerUUID,
			"start": start.Format(time.RFC3339),
			"end":   end.Format(time.RFC3339),
			"limit": strconv.Itoa(limit),
		})
		return nil, err
	}
	defer txx.Rollback()

	_, err = txx.ExecContext(ctx, fmt.Sprintf("SET search_path TO %s", pq.QuoteIdentifier(p.schema)))
	if err != nil {
		err := fmt.Errorf("failed to set search path: %w", err)
		reporting.Report(ctx, err, map[string]string{
			"uuid":   playerUUID,
			"start":  start.Format(time.RFC3339),
			"end":    end.Format(time.RFC3339),
			"limit":  strconv.Itoa(limit),
			"schema": p.schema,
		})
		return nil, err
	}

	// NOTE: Odd limit values will be rounded down (limit=3 == limit=2)
	numberOfIntervals := limit / 2

	intervalLength := timespan / time.Duration(numberOfIntervals)
	for offset := 0; offset < numberOfIntervals; offset++ {
		intervalStart := start.Add(intervalLength * time.Duration(offset))
		intervalEnd := start.Add(intervalLength * time.Duration(offset+1))

		endOperator := "<"
		isLastInterval := offset == numberOfIntervals-1
		if isLastInterval {
			// Inclusive end for last interval
			endOperator = "<="
			// Make sure we get all the way to the end in case of rounding errors
			intervalEnd = end
		}

		var firstStat dbStat
		err = txx.GetContext(
			ctx,
			&firstStat,
			fmt.Sprintf(`select
				id, data_format_version, player_uuid, queried_at, player_data
			from stats
			where
				player_uuid = $1 and
				queried_at >= $2 and
				queried_at %s $3
			order by queried_at asc
			limit 1`, endOperator),
			playerUUID, intervalStart, intervalEnd)

		if errors.Is(err, sql.ErrNoRows) {
			continue
		}
		if err != nil {
			err := fmt.Errorf("failed to select first stat in interval: %w", err)
			reporting.Report(ctx, err, map[string]string{
				"uuid":           playerUUID,
				"start":          start.Format(time.RFC3339),
				"end":            end.Format(time.RFC3339),
				"limit":          strconv.Itoa(limit),
				"intervalStart":  intervalStart.Format(time.RFC3339),
				"intervalEnd":    intervalEnd.Format(time.RFC3339),
				"endOperator":    endOperator,
				"isLastInterval": strconv.FormatBool(isLastInterval),
			})
			return nil, err
		}

		dbStats = append(dbStats, firstStat)

		var lastStat dbStat
		err = txx.GetContext(
			ctx,
			&lastStat,
			fmt.Sprintf(`select
				id, data_format_version, player_uuid, queried_at, player_data
			from stats
			where
				player_uuid = $1 and
				queried_at >= $2 and
				queried_at %s $3
			order by queried_at desc
			limit 1`, endOperator),
			playerUUID, intervalStart, intervalEnd)

		if errors.Is(err, sql.ErrNoRows) {
			continue
		}
		if err != nil {
			err := fmt.Errorf("failed to select last stat in interval: %w", err)
			reporting.Report(ctx, err, map[string]string{
				"uuid":           playerUUID,
				"start":          start.Format(time.RFC3339),
				"end":            end.Format(time.RFC3339),
				"limit":          strconv.Itoa(limit),
				"intervalStart":  intervalStart.Format(time.RFC3339),
				"intervalEnd":    intervalEnd.Format(time.RFC3339),
				"endOperator":    endOperator,
				"isLastInterval": strconv.FormatBool(isLastInterval),
			})
			return nil, err
		}

		if lastStat.ID == firstStat.ID {
			// Only one stat in this interval -> don't add it twice
			continue
		}

		dbStats = append(dbStats, lastStat)
	}

	err = txx.Commit()
	if err != nil {
		err := fmt.Errorf("failed to commit transaction: %w", err)
		reporting.Report(ctx, err, map[string]string{
			"uuid":  playerUUID,
			"start": start.Format(time.RFC3339),
			"end":   end.Format(time.RFC3339),
			"limit": strconv.Itoa(limit),
		})
		return nil, err
	}

	result := make([]domain.PlayerPIT, 0, len(dbStats))
	for _, dbStat := range dbStats {
		playerWithID, err := dbStatToPlayerPITWithID(dbStat)
		if err != nil {
			err := fmt.Errorf("failed to convert db stat to playerpit with id: %w", err)
			reporting.Report(ctx, err, map[string]string{
				"uuid":   playerUUID,
				"start":  start.Format(time.RFC3339),
				"end":    end.Format(time.RFC3339),
				"limit":  strconv.Itoa(limit),
				"statID": dbStat.ID,
			})
			return nil, err
		}
		result = append(result, playerWithID.PlayerPIT)
	}

	return result, nil
}

// NOTE: All domain.PlayerPIT entries must for the same player
func computeSessions(stats []playerPITWithID, start, end time.Time) []domain.Session {
	slices.SortStableFunc(stats, func(a, b playerPITWithID) int {
		if a.QueriedAt.Before(b.QueriedAt) {
			return -1
		}
		if a.QueriedAt.After(b.QueriedAt) {
			return 1
		}
		return 0
	})

	sessions := []domain.Session{}

	getProgressStats := func(stat playerPITWithID) (int, float64) {
		return stat.Overall.GamesPlayed, stat.Experience
	}

	includeSession := func(sessionStart, lastEventfulEntry playerPITWithID) bool {
		if sessionStart.ID == lastEventfulEntry.ID {
			// Session starts and ends with the same entry -> not a session
			return false
		}

		if sessionStart.QueriedAt.After(end) || lastEventfulEntry.QueriedAt.Before(start) {
			// Session does not overlap with requested interval
			return false
		}
		return true
	}

	lastEventfulIndex := -1
	sessionStartIndex := -1

	consecutive := true

	for i := 0; i < len(stats); i++ {
		if sessionStartIndex == -1 {
			// Start a new session
			sessionStartIndex = i
			lastEventfulIndex = i
			consecutive = true
			continue
		}

		if lastEventfulIndex == -1 {
			panic("lastEventfulIndex is -1")
		}

		stat := stats[i]
		sessionStart := stats[sessionStartIndex]
		lastEventfulEntry := stats[lastEventfulIndex]

		// If no activity since session start, move session start to this
		startGamesPlayed, startExperience := getProgressStats(sessionStart)
		currentGamesPlayed, currentExperience := getProgressStats(stat)
		if currentGamesPlayed == startGamesPlayed && currentExperience == startExperience {
			sessionStartIndex = i
			lastEventfulIndex = i
			continue
		}

		// If more than 60 minutes since last activity, end session
		if stat.QueriedAt.Sub(lastEventfulEntry.QueriedAt) > 60*time.Minute {
			if includeSession(sessionStart, lastEventfulEntry) {
				sessions = append(sessions, domain.Session{
					Start:       sessionStart.PlayerPIT,
					End:         lastEventfulEntry.PlayerPIT,
					Consecutive: consecutive,
				})
			}
			// Jump back to right after the last eventful entry (loop adds one)
			// This makes sure we include any non-eventful trailing entries, as they could
			// be the start of a new session.
			// E.g. 1, 2, 3, 4, 4, 4, 5, 6, 7 - we don't want to skip over all the 4s and do
			// 1-4, 5-7, we want 1-4, 4-7
			i = lastEventfulIndex
			sessionStartIndex = -1
			lastEventfulIndex = -1
			continue
		}

		lastEventfulGamesPlayed, lastEventfulExperience := getProgressStats(lastEventfulEntry)

		// Games played changed by more than 1
		if lastEventfulGamesPlayed != currentGamesPlayed && lastEventfulGamesPlayed+1 != currentGamesPlayed {
			consecutive = false
		}

		// Stats changed
		if lastEventfulGamesPlayed != currentGamesPlayed || lastEventfulExperience != currentExperience {
			lastEventfulIndex = i
		}
	}

	// Add the last session if it was not added by the loop due to inactivity
	sessionStart := stats[sessionStartIndex]
	lastEventfulEntry := stats[lastEventfulIndex]

	if includeSession(sessionStart, lastEventfulEntry) {
		sessions = append(sessions, domain.Session{
			Start:       sessionStart.PlayerPIT,
			End:         lastEventfulEntry.PlayerPIT,
			Consecutive: consecutive,
		})
	}

	return sessions
}

func (p *PostgresPlayerRepository) GetSessions(ctx context.Context, playerUUID string, start, end time.Time) ([]domain.Session, error) {
	timespan := end.Sub(start)
	if timespan <= 0 {
		// TODO: Use known error
		err := fmt.Errorf("end time must be after start time")
		reporting.Report(ctx, err, map[string]string{
			"uuid":     playerUUID,
			"start":    start.Format(time.RFC3339),
			"end":      end.Format(time.RFC3339),
			"timespan": timespan.String(),
		})
		return nil, err
	}
	if timespan >= 60*24*time.Hour {
		// TODO: Use known error
		err := fmt.Errorf("timespan too long")
		reporting.Report(ctx, err, map[string]string{
			"uuid":     playerUUID,
			"start":    start.Format(time.RFC3339),
			"end":      end.Format(time.RFC3339),
			"timespan": timespan.String(),
		})
		return nil, err
	}

	// Add some padding on both sides to try to complete sessions that cross the interval borders
	filterStart := start.Add(-24 * time.Hour)
	filterEnd := end.Add(24 * time.Hour)

	dbStats := []dbStat{}

	conn, err := p.db.Connx(ctx)
	if err != nil {
		err := fmt.Errorf("failed to get connection: %w", err)
		reporting.Report(ctx, err, map[string]string{
			"uuid":  playerUUID,
			"start": start.Format(time.RFC3339),
			"end":   end.Format(time.RFC3339),
		})
		return nil, err
	}
	defer conn.Close()

	_, err = conn.ExecContext(ctx, fmt.Sprintf("SET search_path TO %s", pq.QuoteIdentifier(p.schema)))
	if err != nil {
		err := fmt.Errorf("failed to set search path: %w", err)
		reporting.Report(ctx, err, map[string]string{
			"uuid":   playerUUID,
			"start":  start.Format(time.RFC3339),
			"end":    end.Format(time.RFC3339),
			"schema": p.schema,
		})
		return nil, err
	}

	lastID := "00000000-0000-0000-0000-000000000000" // Initial cursor
	for true {
		batch := make([]dbStat, 0, 100)
		// TODO: Index on (id, player_uuid, queried_at)?
		err = conn.SelectContext(
			ctx,
			&batch,
			`select
				id, data_format_version, player_uuid, queried_at, player_data
			from stats
			where
				id > $1 and
				player_uuid = $2 and
				queried_at >= $3 and
				queried_at <= $4
			order by id asc
			limit 100`,
			lastID, playerUUID, filterStart, filterEnd)
		if err != nil {
			err := fmt.Errorf("failed to select batch of stats: %w", err)
			reporting.Report(ctx, err, map[string]string{
				"uuid":        playerUUID,
				"start":       start.Format(time.RFC3339),
				"end":         end.Format(time.RFC3339),
				"filterStart": filterStart.Format(time.RFC3339),
				"filterEnd":   filterEnd.Format(time.RFC3339),
				"lastID":      lastID,
			})
			return nil, err
		}
		if len(batch) == 0 {
			break
		}
		dbStats = append(dbStats, batch...)
		lastID = batch[len(batch)-1].ID
	}

	if len(dbStats) == 0 {
		return nil, nil
	}

	stats := make([]playerPITWithID, 0, len(dbStats))
	for _, dbStat := range dbStats {
		playerWithID, err := dbStatToPlayerPITWithID(dbStat)
		if err != nil {
			err := fmt.Errorf("failed to convert db stat to playerpit with id: %w", err)
			reporting.Report(ctx, err, map[string]string{
				"uuid":   playerUUID,
				"start":  start.Format(time.RFC3339),
				"end":    end.Format(time.RFC3339),
				"statID": dbStat.ID,
			})
			return nil, err
		}
		stats = append(stats, *playerWithID)
	}

	return computeSessions(stats, start, end), nil
}

type StubPlayerRepository struct{}

func (p *StubPlayerRepository) StorePlayer(ctx context.Context, player *domain.PlayerPIT) error {
	return nil
}

func (p *StubPlayerRepository) GetHistory(ctx context.Context, playerUUID string, start, end time.Time, limit int) ([]domain.PlayerPIT, error) {
	return []domain.PlayerPIT{}, nil
}

func (p *StubPlayerRepository) GetSessions(ctx context.Context, playerUUID string, start, end time.Time) ([]domain.Session, error) {
	return []domain.Session{}, nil
}

func NewStubPlayerRepository() *StubPlayerRepository {
	return &StubPlayerRepository{}
}

func NewPostgresPlayerRepositoryOrMock(conf config.Config, logger *slog.Logger) (PlayerRepository, error) {
	var connectionString string
	if conf.IsDevelopment() {
		connectionString = LOCAL_CONNECTION_STRING
	} else {
		connectionString = GetCloudSQLConnectionString(conf.DBUsername(), conf.DBPassword(), conf.CloudSQLUnixSocketPath())
	}

	repositorySchemaName := GetSchemaName(!conf.IsProduction())

	logger.Info("Initializing database connection")
	db, err := NewPostgresDatabase(connectionString)

	if err == nil {
		NewDatabaseMigrator(db, logger.With("component", "migrator")).Migrate(repositorySchemaName)
		return NewPostgresPlayerRepository(db, repositorySchemaName), nil
	}

	if conf.IsDevelopment() {
		logger.Warn("Failed to connect to database. Falling back to stub repository.", "errror", err.Error())
		return NewStubPlayerRepository(), nil
	}

	return nil, fmt.Errorf("Failed to connect to database: %w", err)
}
