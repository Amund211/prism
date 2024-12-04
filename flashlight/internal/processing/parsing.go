package processing

import (
	"context"
	"encoding/json"

	"github.com/Amund211/flashlight/internal/logging"
)

type hypixelAPIResponse struct {
	Success bool              `json:"success"`
	Player  *HypixelAPIPlayer `json:"player"`
	Cause   *string           `json:"cause,omitempty"`
}

type HypixelAPIPlayer struct {
	UUID        *string          `json:"uuid,omitempty"`
	Displayname *string          `json:"displayname,omitempty"`
	LastLogin   *int             `json:"lastLogin,omitempty"`
	LastLogout  *int             `json:"lastLogout,omitempty"`
	Stats       *HypixelAPIStats `json:"stats,omitempty"`
}

type HypixelAPIStats struct {
	Bedwars *HypixelAPIBedwarsStats `json:"Bedwars,omitempty"`
}

type HypixelAPIBedwarsStats struct {
	Experience *float64 `json:"Experience,omitempty"`

	Winstreak   *int `json:"winstreak,omitempty"`
	GamesPlayed *int `json:"games_played_bedwars,omitempty"`
	Wins        *int `json:"wins_bedwars,omitempty"`
	Losses      *int `json:"losses_bedwars,omitempty"`
	BedsBroken  *int `json:"beds_broken_bedwars,omitempty"`
	BedsLost    *int `json:"beds_lost_bedwars,omitempty"`
	FinalKills  *int `json:"final_kills_bedwars,omitempty"`
	FinalDeaths *int `json:"final_deaths_bedwars,omitempty"`
	Kills       *int `json:"kills_bedwars,omitempty"`
	Deaths      *int `json:"deaths_bedwars,omitempty"`

	SoloWinstreak   *int `json:"eight_one_winstreak,omitempty"`
	SoloGamesPlayed *int `json:"eight_one_games_played_bedwars,omitempty"`
	SoloWins        *int `json:"eight_one_wins_bedwars,omitempty"`
	SoloLosses      *int `json:"eight_one_losses_bedwars,omitempty"`
	SoloBedsBroken  *int `json:"eight_one_beds_broken_bedwars,omitempty"`
	SoloBedsLost    *int `json:"eight_one_beds_lost_bedwars,omitempty"`
	SoloFinalKills  *int `json:"eight_one_final_kills_bedwars,omitempty"`
	SoloFinalDeaths *int `json:"eight_one_final_deaths_bedwars,omitempty"`
	SoloKills       *int `json:"eight_one_kills_bedwars,omitempty"`
	SoloDeaths      *int `json:"eight_one_deaths_bedwars,omitempty"`

	DoublesWinstreak   *int `json:"eight_two_winstreak,omitempty"`
	DoublesGamesPlayed *int `json:"eight_two_games_played_bedwars,omitempty"`
	DoublesWins        *int `json:"eight_two_wins_bedwars,omitempty"`
	DoublesLosses      *int `json:"eight_two_losses_bedwars,omitempty"`
	DoublesBedsBroken  *int `json:"eight_two_beds_broken_bedwars,omitempty"`
	DoublesBedsLost    *int `json:"eight_two_beds_lost_bedwars,omitempty"`
	DoublesFinalKills  *int `json:"eight_two_final_kills_bedwars,omitempty"`
	DoublesFinalDeaths *int `json:"eight_two_final_deaths_bedwars,omitempty"`
	DoublesKills       *int `json:"eight_two_kills_bedwars,omitempty"`
	DoublesDeaths      *int `json:"eight_two_deaths_bedwars,omitempty"`

	ThreesWinstreak   *int `json:"four_three_winstreak,omitempty"`
	ThreesGamesPlayed *int `json:"four_three_games_played_bedwars,omitempty"`
	ThreesWins        *int `json:"four_three_wins_bedwars,omitempty"`
	ThreesLosses      *int `json:"four_three_losses_bedwars,omitempty"`
	ThreesBedsBroken  *int `json:"four_three_beds_broken_bedwars,omitempty"`
	ThreesBedsLost    *int `json:"four_three_beds_lost_bedwars,omitempty"`
	ThreesFinalKills  *int `json:"four_three_final_kills_bedwars,omitempty"`
	ThreesFinalDeaths *int `json:"four_three_final_deaths_bedwars,omitempty"`
	ThreesKills       *int `json:"four_three_kills_bedwars,omitempty"`
	ThreesDeaths      *int `json:"four_three_deaths_bedwars,omitempty"`

	FoursWinstreak   *int `json:"four_four_winstreak,omitempty"`
	FoursGamesPlayed *int `json:"four_four_games_played_bedwars,omitempty"`
	FoursWins        *int `json:"four_four_wins_bedwars,omitempty"`
	FoursLosses      *int `json:"four_four_losses_bedwars,omitempty"`
	FoursBedsBroken  *int `json:"four_four_beds_broken_bedwars,omitempty"`
	FoursBedsLost    *int `json:"four_four_beds_lost_bedwars,omitempty"`
	FoursFinalKills  *int `json:"four_four_final_kills_bedwars,omitempty"`
	FoursFinalDeaths *int `json:"four_four_final_deaths_bedwars,omitempty"`
	FoursKills       *int `json:"four_four_kills_bedwars,omitempty"`
	FoursDeaths      *int `json:"four_four_deaths_bedwars,omitempty"`
}

func ParsePlayerData(ctx context.Context, data []byte) (*hypixelAPIResponse, error) {
	logger := logging.FromContext(ctx)
	var response hypixelAPIResponse

	err := json.Unmarshal(data, &response)
	if err != nil {
		logger.Error("Failed to unmarshal player data", "error", err)
		return nil, err
	}
	return &response, nil
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
