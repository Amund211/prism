package function

import (
	"log"
	"net/http"
	"os"
	"time"

	"github.com/Amund211/flashlight/internal/cache"
	"github.com/Amund211/flashlight/internal/getstats"
	"github.com/Amund211/flashlight/internal/hypixel"
	"github.com/Amund211/flashlight/internal/ratelimiting"
	"github.com/Amund211/flashlight/internal/server"

	"github.com/GoogleCloudPlatform/functions-framework-go/functions"
)

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
		server.RateLimitMiddleware(
			rateLimiter,
			server.MakeServeGetPlayerData(
				func(uuid string) ([]byte, int, error) {
					return getstats.GetOrCreateMinifiedPlayerData(playerCache, hypixelAPI, uuid)
				},
			),
		),
	)

	log.Println("Init complete")
}
