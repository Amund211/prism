package ports

import (
	"encoding/json"

	"github.com/Amund211/flashlight/internal/domain"
)

// Prism expects a hypixel API response
type hypixelAPIResponse struct {
	Success bool              `json:"success"`
	Player  *hypixelAPIPlayer `json:"player"`
	Cause   *string           `json:"cause,omitempty"`
}

type hypixelAPIPlayer struct {
	UUID        *string          `json:"uuid,omitempty"`
	Displayname *string          `json:"displayname,omitempty"`
	LastLogin   *int64           `json:"lastLogin,omitempty"`
	LastLogout  *int64           `json:"lastLogout,omitempty"`
	Stats       *hypixelAPIStats `json:"stats,omitempty"`
}

type hypixelAPIStats struct {
	Bedwars *hypixelAPIBedwarsStats `json:"Bedwars,omitempty"`
}

type hypixelAPIBedwarsStats struct {
	Experience float64 `json:"Experience,omitempty"`

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
		Experience: player.Experience,

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
