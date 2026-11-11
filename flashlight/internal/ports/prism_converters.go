package ports

import (
	"encoding/json/v2"

	"github.com/Amund211/prism/flashlight/internal/domain"
)

// Prism expects a hypixel API response
type hypixelAPIResponse struct {
	Success bool              `json:"success"`
	Player  *hypixelAPIPlayer `json:"player"`
	Cause   *string           `json:"cause,omitzero"`
}

type hypixelAPIPlayer struct {
	UUID        *string          `json:"uuid,omitzero"`
	Displayname *string          `json:"displayname,omitzero"`
	LastLogin   *int64           `json:"lastLogin,omitzero"`
	LastLogout  *int64           `json:"lastLogout,omitzero"`
	Stats       *hypixelAPIStats `json:"stats,omitzero"`
}

type hypixelAPIStats struct {
	Bedwars *hypixelAPIBedwarsStats `json:"Bedwars,omitzero"`
}

type hypixelAPIBedwarsStats struct {
	Experience float64 `json:"Experience,omitzero"`

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

func playerToPrismPlayerDataResponse(player *domain.PlayerPIT) *hypixelAPIResponse {
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

	bedwarsStats := hypixelAPIBedwarsStats{
		Experience: float64(player.Experience),

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

		Fourv4Winstreak:   player.Fourv4.Winstreak,
		Fourv4GamesPlayed: player.Fourv4.GamesPlayed,
		Fourv4Wins:        player.Fourv4.Wins,
		Fourv4Losses:      player.Fourv4.Losses,
		Fourv4BedsBroken:  player.Fourv4.BedsBroken,
		Fourv4BedsLost:    player.Fourv4.BedsLost,
		Fourv4FinalKills:  player.Fourv4.FinalKills,
		Fourv4FinalDeaths: player.Fourv4.FinalDeaths,
		Fourv4Kills:       player.Fourv4.Kills,
		Fourv4Deaths:      player.Fourv4.Deaths,
	}

	return &hypixelAPIResponse{
		Success: true,
		Player: &hypixelAPIPlayer{
			UUID:        &player.UUID,
			Displayname: player.Displayname,
			LastLogin:   lastLogin,
			LastLogout:  lastLogout,
			Stats: &hypixelAPIStats{
				Bedwars: &bedwarsStats,
			},
		},
	}
}

func PlayerToPrismPlayerDataResponseData(player *domain.PlayerPIT) ([]byte, error) {
	data, err := json.Marshal(playerToPrismPlayerDataResponse(player))
	if err != nil {
		return []byte{}, err
	}

	return data, nil
}
