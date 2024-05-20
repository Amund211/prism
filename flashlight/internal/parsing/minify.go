package parsing

import (
	"context"
	"encoding/json"

	"github.com/Amund211/flashlight/internal/logging"
)

type HypixelAPIResponse struct {
	Success bool              `json:"success"`
	Player  *hypixelAPIPlayer `json:"player"`
	Cause   *string           `json:"cause,omitempty"`
}

type hypixelAPIPlayer struct {
	UUID        *string `json:"uuid,omitempty"`
	Displayname *string `json:"displayname,omitempty"`
	LastLogin   *int    `json:"lastLogin,omitempty"`
	LastLogout  *int    `json:"lastLogout,omitempty"`
	Stats       *stats  `json:"stats,omitempty"`
}

type stats struct {
	Bedwars *bedwarsStats `json:"Bedwars,omitempty"`
}

type bedwarsStats struct {
	Experience  *float64 `json:"Experience,omitempty"`
	Winstreak   *int     `json:"winstreak,omitempty"`
	Wins        *int     `json:"wins_bedwars,omitempty"`
	Losses      *int     `json:"losses_bedwars,omitempty"`
	BedsBroken  *int     `json:"beds_broken_bedwars,omitempty"`
	BedsLost    *int     `json:"beds_lost_bedwars,omitempty"`
	FinalKills  *int     `json:"final_kills_bedwars,omitempty"`
	FinalDeaths *int     `json:"final_deaths_bedwars,omitempty"`
	Kills       *int     `json:"kills_bedwars,omitempty"`
	Deaths      *int     `json:"deaths_bedwars,omitempty"`
}

func MinifyPlayerData(ctx context.Context, data []byte) ([]byte, error) {
	logger := logging.FromContext(ctx)
	var response HypixelAPIResponse

	err := json.Unmarshal(data, &response)
	if err != nil {
		logger.Error("Failed to unmarshal player data", "error", err)
		return []byte{}, err
	}

	data, err = json.Marshal(response)
	if err != nil {
		logger.Error("Failed to marshal player data", "error", err)
		return []byte{}, err
	}

	return data, nil
}
