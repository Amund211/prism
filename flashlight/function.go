package function

import (
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/Amund211/flashlight/internal/cache"
	"github.com/Amund211/flashlight/internal/parsing"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/Amund211/flashlight/internal/hypixel"
	e "github.com/Amund211/flashlight/internal/errors"

	"github.com/GoogleCloudPlatform/functions-framework-go/functions"
)

type Handler func(w http.ResponseWriter, r *http.Request)

type HypixelAPIErrorResponse struct {
	Success bool   `json:"success"`
	Cause   string `json:"cause"`
}

func getMinifiedPlayerData(playerCache cache.PlayerCache, hypixelAPI hypixel.HypixelAPI, uuid string) ([]byte, int, error) {
	uuidLength := len(uuid)
	if uuidLength < 10 || uuidLength > 100 {
		return []byte{}, -1, fmt.Errorf("%w: Invalid uuid (length=%d)", e.APIClientError, uuidLength)
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

	playerData, statusCode, err := hypixelAPI.GetPlayerData(uuid)
	if err != nil {
		return []byte{}, -1, err
	}

	if len(playerData) > 0 && playerData[0] == '<' {
		log.Println("Hypixel returned HTML")
		return []byte{}, -1, fmt.Errorf("%w: Hypixel returned HTML", e.APIServerError)
	}

	minifiedPlayerData, err := parsing.MinifyPlayerData(playerData)
	if err != nil {
		return []byte{}, -1, fmt.Errorf("%w: %w", e.APIServerError, err)
	}

	playerCache.Set(uuid, minifiedPlayerData, statusCode, true)
	storedInvalidCacheEntry = false

	return minifiedPlayerData, statusCode, nil
}

func writeErrorResponse(w http.ResponseWriter, err error) {
	if errors.Is(err, e.APIServerError) {
		w.WriteHeader(http.StatusInternalServerError)
	} else if errors.Is(err, e.APIClientError) {
		w.WriteHeader(http.StatusBadRequest)
	} else if errors.Is(err, e.RatelimitExceededError) {
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

func makeServeGetPlayerData(playerCache cache.PlayerCache, hypixelAPI hypixel.HypixelAPI) Handler {
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
			writeErrorResponse(w, e.RatelimitExceededError)
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

	hypixelAPI := hypixel.NewHypixelAPI(httpClient, apiKey)

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
