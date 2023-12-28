package function

import (
	"encoding/json"
	"errors"
	"fmt"
	"io/fs"
	"io/ioutil"
	"log"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"github.com/GoogleCloudPlatform/functions-framework-go/functions"
	"github.com/jellydator/ttlcache/v3"
)

type HypixelAPIErrorResponse struct {
	Success bool   `json:"success"`
	Cause   string `json:"cause"`
}

type HypixelAPIResponse struct {
	Success bool              `json:"success"`
	Player  *HypixelAPIPlayer `json:"player"`
	Cause   *string           `json:"cause,omitempty"`
}

type HypixelAPIPlayer struct {
	UUID        *string `json:"uuid,omitempty"`
	Displayname *string `json:"displayname,omitempty"`
	Stats       *Stats  `json:"stats,omitempty"`
}

type Stats struct {
	Bedwars *BedwarsStats `json:"Bedwars,omitempty"`
}

type BedwarsStats struct {
	Experience  *int `json:"Experience,omitempty"`
	Winstreak   *int `json:"winstreak,omitempty"`
	Wins        *int `json:"wins_bedwars,omitempty"`
	Losses      *int `json:"losses_bedwars,omitempty"`
	BedsBroken  *int `json:"beds_broken_bedwars,omitempty"`
	BedsLost    *int `json:"beds_lost_bedwars,omitempty"`
	FinalKills  *int `json:"final_kills_bedwars,omitempty"`
	FinalDeaths *int `json:"final_deaths_bedwars,omitempty"`
	Kills       *int `json:"kills_bedwars,omitempty"`
	Deaths      *int `json:"deaths_bedwars,omitempty"`
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
	getPlayerData(uuid string) ([]byte, int, error)
}

type CachedResponse struct {
	data       []byte
	statusCode int
	valid      bool
}

type HypixelAPIImpl struct {
	httpClient *http.Client
	cache      *ttlcache.Cache[string, CachedResponse]
	apiKey     string
}

func (hypixelAPI HypixelAPIImpl) getPlayerData(uuid string) ([]byte, int, error) {
	log.Println("Incoming request")
	uuidLength := len(uuid)
	if uuidLength < 10 || uuidLength > 100 {
		return []byte{}, -1, fmt.Errorf("%w: Invalid uuid (length=%d)", APIClientError, uuidLength)
	}

	var item *ttlcache.Item[string, CachedResponse]
	var existed bool
	var invalid = CachedResponse{valid: false}

	var storedInvalidCacheEntry = false

	// Delete the cache entry if we somehow fail so another request can try again
	defer func() {
		if storedInvalidCacheEntry {
			hypixelAPI.cache.Delete(uuid)
		}
	}()

	for true {
		item, existed = hypixelAPI.cache.GetOrSet(uuid, invalid)
		if !existed {
			// No entry existed, so we communicate to other requests that we are fetching data
			// Make sure to delete the invalid cache entry if we fail
			storedInvalidCacheEntry = true
			break
		}
		if item.Value().valid {
			// Cache hit
			log.Println("Got cache hit")
			return item.Value().data, item.Value().statusCode, nil
		}
		log.Println("Waiting for cache")
		time.Sleep(500 * time.Millisecond)
	}

	log.Println("Got cache miss -> fetching data")
	time.Sleep(10 * time.Second)
	hypixelAPI.cache.Set(uuid, CachedResponse{
		data:       []byte("{}"),
		statusCode: 200,
		valid:      true},
		ttlcache.DefaultTTL,
	)
	storedInvalidCacheEntry = false
	return []byte("{}"), 200, nil

	url := fmt.Sprintf("https://api.hypixel.net/player?uuid=%s", uuid)
	// return []byte("lol"), 200, nil

	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		log.Println(err)
		return []byte{}, -1, fmt.Errorf("%w: %w", APIServerError, err)
	}

	req.Header.Set("User-Agent", USER_AGENT)
	req.Header.Set("API-Key", hypixelAPI.apiKey)

	resp, err := hypixelAPI.httpClient.Do(req)
	if err != nil {
		log.Println(err)
		return []byte{}, -1, fmt.Errorf("%w: %w", APIServerError, err)
	}

	defer resp.Body.Close()
	data, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		log.Println(err)
		return []byte{}, -1, fmt.Errorf("%w: %w", APIServerError, err)
	}

	if len(data) > 0 && data[0] == '<' {
		return []byte{}, -1, fmt.Errorf("%w: Hypixel returned HTML", APIServerError, uuidLength)
	}

	return data, resp.StatusCode, nil
}

func minifyPlayerData(data []byte) ([]byte, error) {
	var response HypixelAPIResponse

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

func getMinifiedPlayerData(hypixelAPI HypixelAPI, uuid string) ([]byte, int, error) {
	playerData, statusCode, err := hypixelAPI.getPlayerData(uuid)
	if err != nil {
		return []byte{}, -1, err
	}

	minifiedPlayerData, err := minifyPlayerData(playerData)
	if err != nil {
		return []byte{}, -1, fmt.Errorf("%w: %w", APIServerError, err)
	}

	return minifiedPlayerData, statusCode, nil
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

		minifiedPlayerData, statusCode, err := getMinifiedPlayerData(hypixelAPI, uuid)

		if err != nil {
			log.Println("Error getting player data:", err)
			writeErrorResponse(w, err)
			return
		}

		w.WriteHeader(statusCode)
		w.Header().Set("Content-Type", "application/json")
		w.Write(minifiedPlayerData)
	}
}

type HypixelAPIMock struct {
	path       string
	statusCode int
	error      error
}

func (hypixelAPI HypixelAPIMock) getPlayerData(uuid string) ([]byte, int, error) {
	ares := "ares_2023_01_30.json"
	technoblade := "technoblade_2022_06_10.json"
	seeecret := "seeecret_2023_05_14.json"

	chosen := ares
	if uuid == "technoblade" {
		chosen = technoblade
	} else if uuid == "seeecret" {
		chosen = seeecret
	}

	_ = chosen
	// data, err := ioutil.ReadFile(hypixelAPI.path + chosen)
	data, err := ioutil.ReadFile(hypixelAPI.path + uuid)
	if err != nil {
		log.Fatalln(err)
	}
	if hypixelAPI.error != nil {
		return []byte{}, -1, hypixelAPI.error
	}
	if data[0] == '<' {
		return []byte("{}"), -1, nil
	}
	return data, hypixelAPI.statusCode, nil
}

func init() {
	apiKey := os.Getenv("HYPIXEL_API_KEY")
	if apiKey == "" {
		log.Fatalln("Missing Hypixel API key")
	}

	httpClient := &http.Client{}
	cache := ttlcache.New[string, CachedResponse](
		ttlcache.WithTTL[string, CachedResponse](1*time.Minute),
		ttlcache.WithDisableTouchOnHit[string, CachedResponse](),
	)
	go cache.Start()

	hypixelAPI := HypixelAPIImpl{httpClient: httpClient, cache: cache, apiKey: apiKey}

	hypixelAPI2 := HypixelAPIMock{path: "/home/amund/git/prism/tests/data/", error: nil}
	hypixelAPI2 = HypixelAPIMock{path: "", statusCode: 200, error: nil}

	functions.HTTP("flashlight", makeServeGetPlayerData(hypixelAPI))

	log.Println("Init complete")

	_ = hypixelAPI2

	return
	filepath.WalkDir("/home/amund/git/statplot/examples/downloaded_data/", func(path string, dir fs.DirEntry, err error) error {
		if dir.IsDir() || !dir.Type().IsRegular() {
			return nil
		}

		minifiedPlayerData, _, err := getMinifiedPlayerData(hypixelAPI, path)

		// log.Println(string(minifiedPlayerData))
		_ = minifiedPlayerData

		if err != nil {
			log.Println("Error getting player data:", path, err)
		}

		return nil
	})
	log.Println("Done")
}
