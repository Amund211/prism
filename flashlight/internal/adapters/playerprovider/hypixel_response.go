package playerprovider

import (
	"context"
	"encoding/json/v2"
	"fmt"
	"net/http"
	"time"

	"github.com/Amund211/prism/flashlight/internal/domain"
	"github.com/Amund211/prism/flashlight/internal/logging"
	"github.com/Amund211/prism/flashlight/internal/reporting"
)

type hypixelAPIResponse struct {
	Success bool              `json:"success"`
	Player  *HypixelAPIPlayer `json:"player"`
	Cause   *string           `json:"cause,omitzero"`
}

type HypixelAPIPlayer struct {
	UUID        *string          `json:"uuid,omitzero"`
	Displayname *string          `json:"displayname,omitzero"`
	LastLogin   *int64           `json:"lastLogin,omitzero"`
	LastLogout  *int64           `json:"lastLogout,omitzero"`
	Stats       *HypixelAPIStats `json:"stats,omitzero"`
}

type HypixelAPIStats struct {
	Bedwars *HypixelAPIBedwarsStats `json:"Bedwars,omitzero"`
}

type HypixelAPIBedwarsStats struct {
	Experience *float64 `json:"Experience,omitzero"`

	Winstreak   *int `json:"winstreak,omitzero"`
	GamesPlayed int  `json:"games_played_bedwars,omitzero"`
	Wins        int  `json:"wins_bedwars,omitzero"`
	Losses      int  `json:"losses_bedwars,omitzero"`
	BedsBroken  int  `json:"beds_broken_bedwars,omitzero"`
	BedsLost    int  `json:"beds_lost_bedwars,omitzero"`
	FinalKills  int  `json:"final_kills_bedwars,omitzero"`
	FinalDeaths int  `json:"final_deaths_bedwars,omitzero"`
	Kills       int  `json:"kills_bedwars,omitzero"`
	Deaths      int  `json:"deaths_bedwars,omitzero"`

	SoloWinstreak   *int `json:"eight_one_winstreak,omitzero"`
	SoloGamesPlayed int  `json:"eight_one_games_played_bedwars,omitzero"`
	SoloWins        int  `json:"eight_one_wins_bedwars,omitzero"`
	SoloLosses      int  `json:"eight_one_losses_bedwars,omitzero"`
	SoloBedsBroken  int  `json:"eight_one_beds_broken_bedwars,omitzero"`
	SoloBedsLost    int  `json:"eight_one_beds_lost_bedwars,omitzero"`
	SoloFinalKills  int  `json:"eight_one_final_kills_bedwars,omitzero"`
	SoloFinalDeaths int  `json:"eight_one_final_deaths_bedwars,omitzero"`
	SoloKills       int  `json:"eight_one_kills_bedwars,omitzero"`
	SoloDeaths      int  `json:"eight_one_deaths_bedwars,omitzero"`

	DoublesWinstreak   *int `json:"eight_two_winstreak,omitzero"`
	DoublesGamesPlayed int  `json:"eight_two_games_played_bedwars,omitzero"`
	DoublesWins        int  `json:"eight_two_wins_bedwars,omitzero"`
	DoublesLosses      int  `json:"eight_two_losses_bedwars,omitzero"`
	DoublesBedsBroken  int  `json:"eight_two_beds_broken_bedwars,omitzero"`
	DoublesBedsLost    int  `json:"eight_two_beds_lost_bedwars,omitzero"`
	DoublesFinalKills  int  `json:"eight_two_final_kills_bedwars,omitzero"`
	DoublesFinalDeaths int  `json:"eight_two_final_deaths_bedwars,omitzero"`
	DoublesKills       int  `json:"eight_two_kills_bedwars,omitzero"`
	DoublesDeaths      int  `json:"eight_two_deaths_bedwars,omitzero"`

	ThreesWinstreak   *int `json:"four_three_winstreak,omitzero"`
	ThreesGamesPlayed int  `json:"four_three_games_played_bedwars,omitzero"`
	ThreesWins        int  `json:"four_three_wins_bedwars,omitzero"`
	ThreesLosses      int  `json:"four_three_losses_bedwars,omitzero"`
	ThreesBedsBroken  int  `json:"four_three_beds_broken_bedwars,omitzero"`
	ThreesBedsLost    int  `json:"four_three_beds_lost_bedwars,omitzero"`
	ThreesFinalKills  int  `json:"four_three_final_kills_bedwars,omitzero"`
	ThreesFinalDeaths int  `json:"four_three_final_deaths_bedwars,omitzero"`
	ThreesKills       int  `json:"four_three_kills_bedwars,omitzero"`
	ThreesDeaths      int  `json:"four_three_deaths_bedwars,omitzero"`

	FoursWinstreak   *int `json:"four_four_winstreak,omitzero"`
	FoursGamesPlayed int  `json:"four_four_games_played_bedwars,omitzero"`
	FoursWins        int  `json:"four_four_wins_bedwars,omitzero"`
	FoursLosses      int  `json:"four_four_losses_bedwars,omitzero"`
	FoursBedsBroken  int  `json:"four_four_beds_broken_bedwars,omitzero"`
	FoursBedsLost    int  `json:"four_four_beds_lost_bedwars,omitzero"`
	FoursFinalKills  int  `json:"four_four_final_kills_bedwars,omitzero"`
	FoursFinalDeaths int  `json:"four_four_final_deaths_bedwars,omitzero"`
	FoursKills       int  `json:"four_four_kills_bedwars,omitzero"`
	FoursDeaths      int  `json:"four_four_deaths_bedwars,omitzero"`

	Fourv4Winstreak   *int `json:"two_four_winstreak,omitzero"`
	Fourv4GamesPlayed int  `json:"two_four_games_played_bedwars,omitzero"`
	Fourv4Wins        int  `json:"two_four_wins_bedwars,omitzero"`
	Fourv4Losses      int  `json:"two_four_losses_bedwars,omitzero"`
	Fourv4BedsBroken  int  `json:"two_four_beds_broken_bedwars,omitzero"`
	Fourv4BedsLost    int  `json:"two_four_beds_lost_bedwars,omitzero"`
	Fourv4FinalKills  int  `json:"two_four_final_kills_bedwars,omitzero"`
	Fourv4FinalDeaths int  `json:"two_four_final_deaths_bedwars,omitzero"`
	Fourv4Kills       int  `json:"two_four_kills_bedwars,omitzero"`
	Fourv4Deaths      int  `json:"two_four_deaths_bedwars,omitzero"`
}

func ParseHypixelAPIResponse(ctx context.Context, data []byte) (*hypixelAPIResponse, error) {
	response := new(hypixelAPIResponse)

	err := json.Unmarshal(data, response)
	if err != nil {
		logging.FromContext(ctx).ErrorContext(ctx, "Failed to unmarshal player data", "error", err)
		return nil, err
	}
	return response, nil
}

func checkForHypixelError(ctx context.Context, statusCode int, playerData []byte) error {
	// Only support 200 OK
	if statusCode == 200 {
		// Check for HTML response
		if len(playerData) > 0 && playerData[0] == '<' {
			return fmt.Errorf("hypixel API returned HTML (%w)", domain.ErrTemporarilyUnavailable)
		}

		return nil
	}

	// Error for unknown status code
	err := fmt.Errorf("hypixel API returned unsupported status code: %d", statusCode)

	// Errors for known status codes
	switch statusCode {
	case 429:
		err = fmt.Errorf("hypixel ratelimit exceeded (%w)", domain.ErrTemporarilyUnavailable)
	case 500, 502, 503, 504, 520, 521, 522, 523, 524, 525, 526, 527, 530:
		err = fmt.Errorf("hypixel returned status code %d (%s) (%w)", statusCode, http.StatusText(statusCode), domain.ErrTemporarilyUnavailable)
	}

	return err
}

func HypixelAPIResponseToPlayerPIT(ctx context.Context, uuid string, queriedAt time.Time, playerData []byte, statusCode int) (*domain.PlayerPIT, error) {
	if err := checkForHypixelError(ctx, statusCode, playerData); err != nil {
		reporting.Report(
			ctx,
			err,
			map[string]string{
				"statusCode": fmt.Sprint(statusCode),
				"data":       string(playerData),
			},
		)
		logging.FromContext(ctx).ErrorContext(
			ctx,
			"Got response from hypixel",
			"status", "error",
			"error", err.Error(),
			"data", string(playerData),
			"statusCode", statusCode,
			"contentLength", len(playerData),
		)
		return nil, err
	}

	logging.FromContext(ctx).InfoContext(
		ctx,
		"Got response from hypixel",
		"status", "success",
		"statusCode", statusCode,
		"contentLength", len(playerData),
	)

	parsedAPIResponse, err := ParseHypixelAPIResponse(ctx, playerData)
	if err != nil {
		err = fmt.Errorf("failed to parse player data: %w", err)
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
		err := fmt.Errorf("got success=false from Hypixel: %s", cause)
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

	if parsedAPIResponse.Player == nil {
		logging.FromContext(ctx).InfoContext(ctx, "Player not found")
		return nil, domain.ErrPlayerNotFound
	}

	apiPlayer := parsedAPIResponse.Player

	var lastLogin, lastLogout *time.Time
	if apiPlayer.LastLogin != nil {
		// UnixMilli returns a time in the local location; normalize to UTC so
		// serialization is independent of the host's timezone.
		l := time.UnixMilli(*apiPlayer.LastLogin).UTC()
		lastLogin = &l
	}
	if apiPlayer.LastLogout != nil {
		l := time.UnixMilli(*apiPlayer.LastLogout).UTC()
		lastLogout = &l
	}

	var experience int64 = 500
	var solo, doubles, threes, fours, fourv4, overall domain.GamemodeStatsPIT

	if apiPlayer.Stats != nil && apiPlayer.Stats.Bedwars != nil {
		bw := apiPlayer.Stats.Bedwars

		if bw.Experience != nil {
			experience = int64(*bw.Experience)
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

		fourv4 = domain.GamemodeStatsPIT{
			Winstreak:   apiPlayer.Stats.Bedwars.Fourv4Winstreak,
			GamesPlayed: bw.Fourv4GamesPlayed,
			Wins:        bw.Fourv4Wins,
			Losses:      bw.Fourv4Losses,
			BedsBroken:  bw.Fourv4BedsBroken,
			BedsLost:    bw.Fourv4BedsLost,
			FinalKills:  bw.Fourv4FinalKills,
			FinalDeaths: bw.Fourv4FinalDeaths,
			Kills:       bw.Fourv4Kills,
			Deaths:      bw.Fourv4Deaths,
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
		DBID: nil, // This does not come from our db, so it doesn't have an ID there yet

		// Normalize to UTC so serialization is independent of the host's
		// timezone (the caller's clock may be in local time).
		QueriedAt: queriedAt.UTC(),

		UUID: uuid,

		Displayname: apiPlayer.Displayname,
		LastLogin:   lastLogin,
		LastLogout:  lastLogout,

		Experience: experience,
		Solo:       solo,
		Doubles:    doubles,
		Threes:     threes,
		Fours:      fours,
		Fourv4:     fourv4,
		Overall:    overall,
	}, nil
}
