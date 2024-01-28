package function

import (
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/Amund211/flashlight/internal/cache"
	"github.com/Amund211/flashlight/internal/getstats"
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

		minifiedPlayerData, statusCode, err := getstats.GetMinifiedPlayerData(playerCache, hypixelAPI, uuid)

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
