package function

import (
	"encoding/json"
	"errors"
	"fmt"
	"io/ioutil"
	"log"
	"net/http"
	"os"

	"github.com/GoogleCloudPlatform/functions-framework-go/functions"
)

type HypixelAPIErrorResponse struct {
	Success bool   `json:"success"`
	Cause   string `json:"cause"`
}

type HypixelAPISuccessResponse struct {
	Success bool             `json:"success"`
	Player  HypixelAPIPlayer `json:"player"`
}

type BedwarsStats struct {
	Experience  int `json:"Experience"`
	Winstreak   int `json:"winstreak"`
	Wins        int `json:"wins_bedwars"`
	Losses      int `json:"losses_bedwars"`
	BedsBroken  int `json:"beds_broken_bedwars"`
	BedsLost    int `json:"beds_lost_bedwars"`
	FinalKills  int `json:"final_kills_bedwars"`
	FinalDeaths int `json:"final_deaths_bedwars"`
	Kills       int `json:"kills_bedwars"`
	Deaths      int `json:"deaths_bedwars"`
}

type Stats struct {
	Bedwars BedwarsStats `json:"Bedwars"`
}

type HypixelAPIPlayer struct {
	UUID        string `json:"uuid"`
	Displayname string `json:"displayname"`
	Stats       Stats  `json:"stats"`
}

const USER_AGENT = "flashlight/0.1.0 (+https://github.com/Amund211/flashlight)"

var (
	APIServerError         = errors.New("Server error")
	APIClientError         = errors.New("Client error")
	APIKeyError            = errors.New("Invalid API key")
	PlayerNotFoundError    = errors.New("Player not found")
	RatelimitExceededError = errors.New("Ratelimit exceeded")
)

type HypixelAPI interface {
	getPlayerData(uuid string) ([]byte, error)
}

type HypixelAPIImpl struct {
	httpClient *http.Client
	apiKey     string
}

func (hypixelAPI HypixelAPIImpl) getPlayerData(uuid string) ([]byte, error) {
	url := fmt.Sprintf("https://api.hypixel.net/player?uuid=%s", uuid)
	return []byte("lol"), nil

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		log.Println(err)
		return []byte{}, err
	}

	req.Header.Set("User-Agent", USER_AGENT)
	req.Header.Set("API-Key", hypixelAPI.apiKey)

	resp, err := hypixelAPI.httpClient.Do(req)
	if err != nil {
		log.Println(err)
		return []byte{}, err
	}

	defer resp.Body.Close()
	data, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		log.Println(err)
		return []byte{}, err
	}

	return data, nil
}

func minifyPlayerData(data []byte) ([]byte, error) {
	return data, nil
}

func getMinifiedPlayerData(hypixelAPI HypixelAPI, uuid string) ([]byte, error) {
	uuidLength := len(uuid)
	if uuidLength < 10 || uuidLength > 100 {
		return []byte{}, fmt.Errorf("%w: Invalid uuid (length=%d)", APIClientError, uuidLength)
	}

	playerData, err := hypixelAPI.getPlayerData(uuid)
	if err != nil {
		return []byte{}, fmt.Errorf("%w: %w", APIServerError, err)
	}

	minifiedPlayerData, err := minifyPlayerData(playerData)
	if err != nil {
		return []byte{}, fmt.Errorf("%w: %w", APIServerError, err)
	}

	return minifiedPlayerData, nil
}

func writeErrorResponse(w http.ResponseWriter, err error) {
	if errors.Is(err, APIServerError) {
		w.WriteHeader(http.StatusInternalServerError)
	} else if errors.Is(err, APIClientError) {
		w.WriteHeader(http.StatusBadRequest)
	} else {
		w.WriteHeader(http.StatusInternalServerError)
	}

	errorResponse := HypixelAPIErrorResponse{
		Success: false,
		Cause:   err.Error(),
	}

	errorBytes, err := json.Marshal(errorResponse)

	if err != nil {
		log.Println("Error marshalling error response: %w", err)
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte(`{"success":false,"cause":"Internal server error (flashlight)"}`))
		return
	}

	w.Write(errorBytes)
}

func makeServeGetPlayerData(hypixelAPI HypixelAPI) func(w http.ResponseWriter, r *http.Request) {
	return func(w http.ResponseWriter, r *http.Request) {
		uuid := r.URL.Query().Get("uuid")

		minifiedPlayerData, err := getMinifiedPlayerData(hypixelAPI, uuid)

		if err != nil {
			log.Println("Error getting player data:", err)
			writeErrorResponse(w, err)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		w.Write(minifiedPlayerData)
	}
}

func init() {
	apiKey := os.Getenv("HYPIXEL_API_KEY")
	if apiKey == "" {
		log.Fatalln("Missing Hypixel API key")
	}

	httpClient := &http.Client{}

	hypixelAPI := HypixelAPIImpl{httpClient: httpClient, apiKey: apiKey}

	functions.HTTP("flashlight", makeServeGetPlayerData(hypixelAPI))

	log.Println("Init complete")
}
