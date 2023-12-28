package function

import (
	"encoding/json"
	"errors"
	"fmt"
	"io/ioutil"
	"log"
	"net/http"
	"os"
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

type PlayerCache interface {
	GetOrSet(uuid string, value CachedResponse) (CachedResponse, bool)
	Set(uuid string, value CachedResponse)
	Delete(uuid string)
	Wait()
}

type PlayerCacheImpl struct {
	cache *ttlcache.Cache[string, CachedResponse]
}

func (playerCache PlayerCacheImpl) GetOrSet(uuid string, value CachedResponse) (CachedResponse, bool) {
	item, existed := playerCache.cache.GetOrSet(uuid, value)
	return item.Value(), existed
}

func (playerCache PlayerCacheImpl) Set(uuid string, value CachedResponse) {
	playerCache.cache.Set(uuid, value, ttlcache.DefaultTTL)
}

func (playerCache PlayerCacheImpl) Delete(uuid string) {
	playerCache.cache.Delete(uuid)
}

func (playerCache PlayerCacheImpl) Wait() {
	time.Sleep(50 * time.Millisecond)
}

type CachedResponse struct {
	data       []byte
	statusCode int
	valid      bool
}

type HypixelAPIImpl struct {
	httpClient *http.Client
	apiKey     string
}

func getCachedResponse(playerCache PlayerCache, uuid string) CachedResponse {
	var cachedResponse CachedResponse
	var existed bool
	var invalid = CachedResponse{valid: false}

	for true {
		cachedResponse, existed = playerCache.GetOrSet(uuid, invalid)
		if !existed {
			// No entry existed, so we communicate to other requests that we are fetching data
			// Caller must defer playerCache.Delete(uuid) in case they fail
			log.Println("Got cache miss")
			return cachedResponse
		}
		if cachedResponse.valid {
			// Cache hit
			log.Println("Got cache hit")
			return cachedResponse
		}
		log.Println("Waiting for cache")
		playerCache.Wait()
	}
	panic("unreachable")
}

func (hypixelAPI HypixelAPIImpl) getPlayerData(uuid string) ([]byte, int, error) {
	uuidLength := len(uuid)
	if uuidLength < 10 || uuidLength > 100 {
		return []byte{}, -1, fmt.Errorf("%w: Invalid uuid (length=%d)", APIClientError, uuidLength)
	}

	url := fmt.Sprintf("https://api.hypixel.net/player?uuid=%s", uuid)

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
		log.Println("Hypixel returned HTML")
		return []byte{}, -1, fmt.Errorf("%w: Hypixel returned HTML", APIServerError)
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

func getMinifiedPlayerData(playerCache PlayerCache, hypixelAPI HypixelAPI, uuid string) ([]byte, int, error) {
	cachedResponse := getCachedResponse(playerCache, uuid)
	if cachedResponse.valid {
		return cachedResponse.data, cachedResponse.statusCode, nil
	}

	// getCachedResponse inserts an invalid cache entry if it doesn't exist
	// If we fail to store a valid cache entry, we must delete the invalid one so another request can try again
	var storedInvalidCacheEntry = true
	defer func() {
		if storedInvalidCacheEntry {
			playerCache.Delete(uuid)
		}
	}()

	playerData, statusCode, err := hypixelAPI.getPlayerData(uuid)
	if err != nil {
		return []byte{}, -1, err
	}

	minifiedPlayerData, err := minifyPlayerData(playerData)
	if err != nil {
		return []byte{}, -1, fmt.Errorf("%w: %w", APIServerError, err)
	}

	playerCache.Set(uuid, CachedResponse{data: minifiedPlayerData, statusCode: statusCode, valid: true})
	storedInvalidCacheEntry = false

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

func makeServeGetPlayerData(playerCache PlayerCache, hypixelAPI HypixelAPI) func(w http.ResponseWriter, r *http.Request) {
	return func(w http.ResponseWriter, r *http.Request) {
		log.Println("Incoming request")
		uuid := r.URL.Query().Get("uuid")

		minifiedPlayerData, statusCode, err := getMinifiedPlayerData(playerCache, hypixelAPI, uuid)

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

	playerCache := PlayerCacheImpl{cache: cache}

	hypixelAPI := HypixelAPIImpl{httpClient: httpClient, apiKey: apiKey}

	functions.HTTP("flashlight", makeServeGetPlayerData(playerCache, hypixelAPI))

	log.Println("Init complete")
}
