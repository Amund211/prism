package playerprovider

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
	e "github.com/Amund211/flashlight/internal/errors"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/reporting"
)

type hypixelAPIResponse struct {
	Success bool              `json:"success"`
	Player  *HypixelAPIPlayer `json:"player"`
	Cause   *string           `json:"cause,omitempty"`
}

type HypixelAPIPlayer struct {
	UUID        *string          `json:"uuid,omitempty"`
	Displayname *string          `json:"displayname,omitempty"`
	LastLogin   *int64           `json:"lastLogin,omitempty"`
	LastLogout  *int64           `json:"lastLogout,omitempty"`
	Stats       *HypixelAPIStats `json:"stats,omitempty"`
}

type HypixelAPIStats struct {
	Bedwars *HypixelAPIBedwarsStats `json:"Bedwars,omitempty"`
}

type HypixelAPIBedwarsStats struct {
	Experience *float64 `json:"Experience,omitempty"`

	Winstreak   *int `json:"winstreak,omitempty"`
	GamesPlayed int  `json:"games_played_bedwars,omitempty"`
	Wins        int  `json:"wins_bedwars,omitempty"`
	Losses      int  `json:"losses_bedwars,omitempty"`
	BedsBroken  int  `json:"beds_broken_bedwars,omitempty"`
	BedsLost    int  `json:"beds_lost_bedwars,omitempty"`
	FinalKills  int  `json:"final_kills_bedwars,omitempty"`
	FinalDeaths int  `json:"final_deaths_bedwars,omitempty"`
	Kills       int  `json:"kills_bedwars,omitempty"`
	Deaths      int  `json:"deaths_bedwars,omitempty"`

	SoloWinstreak   *int `json:"eight_one_winstreak,omitempty"`
	SoloGamesPlayed int  `json:"eight_one_games_played_bedwars,omitempty"`
	SoloWins        int  `json:"eight_one_wins_bedwars,omitempty"`
	SoloLosses      int  `json:"eight_one_losses_bedwars,omitempty"`
	SoloBedsBroken  int  `json:"eight_one_beds_broken_bedwars,omitempty"`
	SoloBedsLost    int  `json:"eight_one_beds_lost_bedwars,omitempty"`
	SoloFinalKills  int  `json:"eight_one_final_kills_bedwars,omitempty"`
	SoloFinalDeaths int  `json:"eight_one_final_deaths_bedwars,omitempty"`
	SoloKills       int  `json:"eight_one_kills_bedwars,omitempty"`
	SoloDeaths      int  `json:"eight_one_deaths_bedwars,omitempty"`

	DoublesWinstreak   *int `json:"eight_two_winstreak,omitempty"`
	DoublesGamesPlayed int  `json:"eight_two_games_played_bedwars,omitempty"`
	DoublesWins        int  `json:"eight_two_wins_bedwars,omitempty"`
	DoublesLosses      int  `json:"eight_two_losses_bedwars,omitempty"`
	DoublesBedsBroken  int  `json:"eight_two_beds_broken_bedwars,omitempty"`
	DoublesBedsLost    int  `json:"eight_two_beds_lost_bedwars,omitempty"`
	DoublesFinalKills  int  `json:"eight_two_final_kills_bedwars,omitempty"`
	DoublesFinalDeaths int  `json:"eight_two_final_deaths_bedwars,omitempty"`
	DoublesKills       int  `json:"eight_two_kills_bedwars,omitempty"`
	DoublesDeaths      int  `json:"eight_two_deaths_bedwars,omitempty"`

	ThreesWinstreak   *int `json:"four_three_winstreak,omitempty"`
	ThreesGamesPlayed int  `json:"four_three_games_played_bedwars,omitempty"`
	ThreesWins        int  `json:"four_three_wins_bedwars,omitempty"`
	ThreesLosses      int  `json:"four_three_losses_bedwars,omitempty"`
	ThreesBedsBroken  int  `json:"four_three_beds_broken_bedwars,omitempty"`
	ThreesBedsLost    int  `json:"four_three_beds_lost_bedwars,omitempty"`
	ThreesFinalKills  int  `json:"four_three_final_kills_bedwars,omitempty"`
	ThreesFinalDeaths int  `json:"four_three_final_deaths_bedwars,omitempty"`
	ThreesKills       int  `json:"four_three_kills_bedwars,omitempty"`
	ThreesDeaths      int  `json:"four_three_deaths_bedwars,omitempty"`

	FoursWinstreak   *int `json:"four_four_winstreak,omitempty"`
	FoursGamesPlayed int  `json:"four_four_games_played_bedwars,omitempty"`
	FoursWins        int  `json:"four_four_wins_bedwars,omitempty"`
	FoursLosses      int  `json:"four_four_losses_bedwars,omitempty"`
	FoursBedsBroken  int  `json:"four_four_beds_broken_bedwars,omitempty"`
	FoursBedsLost    int  `json:"four_four_beds_lost_bedwars,omitempty"`
	FoursFinalKills  int  `json:"four_four_final_kills_bedwars,omitempty"`
	FoursFinalDeaths int  `json:"four_four_final_deaths_bedwars,omitempty"`
	FoursKills       int  `json:"four_four_kills_bedwars,omitempty"`
	FoursDeaths      int  `json:"four_four_deaths_bedwars,omitempty"`
}

func ParseHypixelAPIResponse(ctx context.Context, data []byte) (*hypixelAPIResponse, error) {
	logger := logging.FromContext(ctx)
	response := new(hypixelAPIResponse)

	err := json.Unmarshal(data, response)
	if err != nil {
		logger.Error("Failed to unmarshal player data", "error", err)
		return nil, err
	}
	return response, nil
}

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

func HypixelAPIResponseToPlayerPIT(ctx context.Context, uuid string, queriedAt time.Time, playerData []byte, statusCode int) (*domain.PlayerPIT, error) {
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
		return nil, err
	}

	logging.FromContext(ctx).Info(
		"Got response from hypixel",
		"status", "success",
		"statusCode", statusCode,
		"contentLength", len(playerData),
	)

	parsedAPIResponse, err := ParseHypixelAPIResponse(ctx, playerData)
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
		return nil, err
	}

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

func MarshalPlayerData(ctx context.Context, response *hypixelAPIResponse) ([]byte, error) {
	logger := logging.FromContext(ctx)
	data, err := json.Marshal(response)
	if err != nil {
		logger.Error("Failed to marshal player data", "error", err)
		return []byte{}, err
	}

	return data, nil
}
