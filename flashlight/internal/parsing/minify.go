package parsing

import (
	"encoding/json"
	"log"
)

type hypixelAPIResponse struct {
	Success bool              `json:"success"`
	Player  *hypixelAPIPlayer `json:"player"`
	Cause   *string           `json:"cause,omitempty"`
}

type hypixelAPIPlayer struct {
	UUID        *string `json:"uuid,omitempty"`
	Displayname *string `json:"displayname,omitempty"`
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

func MinifyPlayerData(data []byte) ([]byte, error) {
	var response hypixelAPIResponse

	err := json.Unmarshal(data, &response)
	if err != nil {
		log.Println(err)
		return []byte{}, err
	}

	data, err = json.Marshal(response)
	if err != nil {
		log.Println(err)
		return []byte{}, err
	}

	return data, nil
}
