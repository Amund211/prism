package function

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/Amund211/flashlight/internal/cache"
	"github.com/Amund211/flashlight/internal/parsing"
	"github.com/Amund211/flashlight/internal/ratelimiting"

	"github.com/GoogleCloudPlatform/functions-framework-go/functions"
)

type Handler func(w http.ResponseWriter, r *http.Request)

type HypixelAPIErrorResponse struct {
	Success bool   `json:"success"`
	Cause   string `json:"cause"`
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

type HypixelAPIImpl struct {
	httpClient *http.Client
	apiKey     string
}

func (hypixelAPI HypixelAPIImpl) getPlayerData(uuid string) ([]byte, int, error) {
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
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		log.Println(err)
		return []byte{}, -1, fmt.Errorf("%w: %w", APIServerError, err)
	}

	return data, resp.StatusCode, nil
}

func getMinifiedPlayerData(playerCache cache.PlayerCache, hypixelAPI HypixelAPI, uuid string) ([]byte, int, error) {
	uuidLength := len(uuid)
	if uuidLength < 10 || uuidLength > 100 {
		return []byte{}, -1, fmt.Errorf("%w: Invalid uuid (length=%d)", APIClientError, uuidLength)
	}

	cachedResponse := cache.GetOrCreateCachedResponse(playerCache, uuid)
	if cachedResponse.Valid {
		return cachedResponse.Data, cachedResponse.StatusCode, nil
	}

	// getOrCreateCachedResponse inserts an invalid cache entry if it doesn't exist
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

	if len(playerData) > 0 && playerData[0] == '<' {
		log.Println("Hypixel returned HTML")
		return []byte{}, -1, fmt.Errorf("%w: Hypixel returned HTML", APIServerError)
	}

	minifiedPlayerData, err := parsing.MinifyPlayerData(playerData)
	if err != nil {
		return []byte{}, -1, fmt.Errorf("%w: %w", APIServerError, err)
	}

	playerCache.Set(uuid, minifiedPlayerData, statusCode, true)
	storedInvalidCacheEntry = false

	return minifiedPlayerData, statusCode, nil
}

func writeErrorResponse(w http.ResponseWriter, err error) {
	if errors.Is(err, APIServerError) {
		w.WriteHeader(http.StatusInternalServerError)
	} else if errors.Is(err, APIClientError) {
		w.WriteHeader(http.StatusBadRequest)
	} else if errors.Is(err, RatelimitExceededError) {
		w.WriteHeader(http.StatusTooManyRequests)
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

func makeServeGetPlayerData(playerCache cache.PlayerCache, hypixelAPI HypixelAPI) Handler {
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

func rateLimitMiddleware(rateLimiter ratelimiting.RateLimiter, next Handler) Handler {
	return func(w http.ResponseWriter, r *http.Request) {
		if !rateLimiter.Allow(r.RemoteAddr) {
			writeErrorResponse(w, RatelimitExceededError)
			return
		}

		next(w, r)
	}
}

func init() {
	apiKey := os.Getenv("HYPIXEL_API_KEY")
	if apiKey == "" {
		log.Fatalln("Missing Hypixel API key")
	}

	httpClient := &http.Client{}

	playerCache := cache.NewPlayerCache(1 * time.Minute)

	hypixelAPI := HypixelAPIImpl{httpClient: httpClient, apiKey: apiKey}

	rateLimiter := ratelimiting.NewIPBasedRateLimiter(2, 120)

	functions.HTTP(
		"flashlight",
		rateLimitMiddleware(
			rateLimiter,
			makeServeGetPlayerData(playerCache, hypixelAPI),
		),
	)

	log.Println("Init complete")
}
