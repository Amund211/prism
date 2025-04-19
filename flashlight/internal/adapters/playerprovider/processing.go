package playerprovider

import (
	"context"
	"fmt"
	"net/http"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
	e "github.com/Amund211/flashlight/internal/errors"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/reporting"
)

func checkForHypixelError(ctx context.Context, statusCode int, playerData []byte) error {
	// Only support 200 OK
	if statusCode == 200 {
		// Check for HTML response
		if len(playerData) > 0 && playerData[0] == '<' {
			return fmt.Errorf("%w: Hypixel API returned HTML %w", e.APIServerError, e.RetriableError)
		}

		return nil
	}

	// Error for unknown status code
	err := fmt.Errorf("%w: Hypixel API returned unsupported status code: %d", e.APIServerError, statusCode)

	// Errors for known status codes
	switch statusCode {
	case 429:
		err = fmt.Errorf("%w: Hypixel ratelimit exceeded %w", e.RatelimitExceededError, e.RetriableError)
	case 500, 502, 503, 504, 520, 521, 522, 523, 524, 525, 526, 527, 530:
		err = fmt.Errorf("%w: Hypixel returned status code %d (%s) %w", e.APIServerError, statusCode, http.StatusText(statusCode), e.RetriableError)
	}

	return err
}

func ParseHypixelAPIResponse(ctx context.Context, playerData []byte, statusCode int) (*hypixelAPIResponse, int, error) {
	err := checkForHypixelError(ctx, statusCode, playerData)
	if err != nil {
		reporting.Report(
			ctx,
			err,
			map[string]string{
				"statusCode": fmt.Sprint(statusCode),
				"data":       string(playerData),
			},
		)
		logging.FromContext(ctx).Error(
			"Got response from hypixel",
			"status", "error",
			"error", err.Error(),
			"data", string(playerData),
			"statusCode", statusCode,
			"contentLength", len(playerData),
		)
		return nil, -1, err
	}

	logging.FromContext(ctx).Info(
		"Got response from hypixel",
		"status", "success",
		"statusCode", statusCode,
		"contentLength", len(playerData),
	)

	parsedPlayerData, err := ParsePlayerData(ctx, playerData)
	if err != nil {
		err = fmt.Errorf("%w: failed to parse player data: %w", e.APIServerError, err)
		reporting.Report(
			ctx,
			err,
			map[string]string{
				"statusCode": fmt.Sprint(statusCode),
				"data":       string(playerData),
			},
		)
		return nil, -1, err
	}

	processedStatusCode := 200
	if parsedPlayerData.Success && parsedPlayerData.Player == nil {
		processedStatusCode = 404
	}

	return parsedPlayerData, processedStatusCode, nil
}

func HypixelAPIResponseToDomainPlayer(parsedAPIResponse *hypixelAPIResponse, queriedAt time.Time, flashlightStatID *string) (*domain.PlayerPIT, error) {
	if !parsedAPIResponse.Success {
		cause := "unknown error (flashlight)"
		if parsedAPIResponse.Cause != nil {
			cause = *parsedAPIResponse.Cause
		}
		return nil, fmt.Errorf("%w: %s", e.APIServerError, cause)
	}

	if parsedAPIResponse.Player == nil {
		// TODO: ErrPlayerNotFound?
		return nil, nil
	}

	apiPlayer := parsedAPIResponse.Player

	if apiPlayer.UUID == nil {
		return nil, fmt.Errorf("%w: %s", e.APIServerError, "missing uuid")
	}
	uuid := *apiPlayer.UUID

	var lastLogin, lastLogout *time.Time
	if apiPlayer.LastLogin != nil {
		l := time.UnixMilli(*apiPlayer.LastLogin)
		lastLogin = &l
	}
	if apiPlayer.LastLogout != nil {
		l := time.UnixMilli(*apiPlayer.LastLogout)
		lastLogout = &l
	}

	experience := 500.0
	var solo, doubles, threes, fours, overall domain.GamemodeStatsPIT

	if apiPlayer.Stats != nil && apiPlayer.Stats.Bedwars != nil {
		bw := apiPlayer.Stats.Bedwars

		if bw.Experience != nil {
			experience = *bw.Experience
		}

		solo = domain.GamemodeStatsPIT{
			Winstreak:   apiPlayer.Stats.Bedwars.SoloWinstreak,
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

		doubles = domain.GamemodeStatsPIT{
			Winstreak:   apiPlayer.Stats.Bedwars.DoublesWinstreak,
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

		threes = domain.GamemodeStatsPIT{
			Winstreak:   apiPlayer.Stats.Bedwars.ThreesWinstreak,
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

		fours = domain.GamemodeStatsPIT{
			Winstreak:   apiPlayer.Stats.Bedwars.FoursWinstreak,
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

		overall = domain.GamemodeStatsPIT{
			Winstreak:   apiPlayer.Stats.Bedwars.Winstreak,
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
	}

	return &domain.PlayerPIT{
		QueriedAt: queriedAt,

		UUID: uuid,

		Displayname: apiPlayer.Displayname,
		LastLogin:   lastLogin,
		LastLogout:  lastLogout,

		Experience: experience,
		Solo:       solo,
		Doubles:    doubles,
		Threes:     threes,
		Fours:      fours,
		Overall:    overall,
	}, nil
}

func DomainPlayerToHypixelAPIResponse(player *domain.PlayerPIT) *hypixelAPIResponse {
	if player == nil {
		return &hypixelAPIResponse{
			Success: true,
			Player:  nil,
		}
	}

	var lastLogin, lastLogout *int64
	if player.LastLogin != nil {
		l := player.LastLogin.UnixMilli()
		lastLogin = &l
	}
	if player.LastLogout != nil {
		l := player.LastLogout.UnixMilli()
		lastLogout = &l
	}

	bedwarsStats := HypixelAPIBedwarsStats{
		Experience: &player.Experience,

		Winstreak:   player.Overall.Winstreak,
		GamesPlayed: player.Overall.GamesPlayed,
		Wins:        player.Overall.Wins,
		Losses:      player.Overall.Losses,
		BedsBroken:  player.Overall.BedsBroken,
		BedsLost:    player.Overall.BedsLost,
		FinalKills:  player.Overall.FinalKills,
		FinalDeaths: player.Overall.FinalDeaths,
		Kills:       player.Overall.Kills,
		Deaths:      player.Overall.Deaths,

		SoloWinstreak:   player.Solo.Winstreak,
		SoloGamesPlayed: player.Solo.GamesPlayed,
		SoloWins:        player.Solo.Wins,
		SoloLosses:      player.Solo.Losses,
		SoloBedsBroken:  player.Solo.BedsBroken,
		SoloBedsLost:    player.Solo.BedsLost,
		SoloFinalKills:  player.Solo.FinalKills,
		SoloFinalDeaths: player.Solo.FinalDeaths,
		SoloKills:       player.Solo.Kills,
		SoloDeaths:      player.Solo.Deaths,

		DoublesWinstreak:   player.Doubles.Winstreak,
		DoublesGamesPlayed: player.Doubles.GamesPlayed,
		DoublesWins:        player.Doubles.Wins,
		DoublesLosses:      player.Doubles.Losses,
		DoublesBedsBroken:  player.Doubles.BedsBroken,
		DoublesBedsLost:    player.Doubles.BedsLost,
		DoublesFinalKills:  player.Doubles.FinalKills,
		DoublesFinalDeaths: player.Doubles.FinalDeaths,
		DoublesKills:       player.Doubles.Kills,
		DoublesDeaths:      player.Doubles.Deaths,

		ThreesWinstreak:   player.Threes.Winstreak,
		ThreesGamesPlayed: player.Threes.GamesPlayed,
		ThreesWins:        player.Threes.Wins,
		ThreesLosses:      player.Threes.Losses,
		ThreesBedsBroken:  player.Threes.BedsBroken,
		ThreesBedsLost:    player.Threes.BedsLost,
		ThreesFinalKills:  player.Threes.FinalKills,
		ThreesFinalDeaths: player.Threes.FinalDeaths,
		ThreesKills:       player.Threes.Kills,
		ThreesDeaths:      player.Threes.Deaths,

		FoursWinstreak:   player.Fours.Winstreak,
		FoursGamesPlayed: player.Fours.GamesPlayed,
		FoursWins:        player.Fours.Wins,
		FoursLosses:      player.Fours.Losses,
		FoursBedsBroken:  player.Fours.BedsBroken,
		FoursBedsLost:    player.Fours.BedsLost,
		FoursFinalKills:  player.Fours.FinalKills,
		FoursFinalDeaths: player.Fours.FinalDeaths,
		FoursKills:       player.Fours.Kills,
		FoursDeaths:      player.Fours.Deaths,
	}

	return &hypixelAPIResponse{
		Success: true,
		Player: &HypixelAPIPlayer{
			UUID:        &player.UUID,
			Displayname: player.Displayname,
			LastLogin:   lastLogin,
			LastLogout:  lastLogout,
			Stats: &HypixelAPIStats{
				Bedwars: &bedwarsStats,
			},
		},
	}
}
