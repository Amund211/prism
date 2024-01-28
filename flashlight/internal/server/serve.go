package server

import (
    "log"
    "net/http"

    "github.com/Amund211/flashlight/internal/cache"
    "github.com/Amund211/flashlight/internal/getstats"
    "github.com/Amund211/flashlight/internal/hypixel"
)

func MakeServeGetPlayerData(playerCache cache.PlayerCache, hypixelAPI hypixel.HypixelAPI) Handler {
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
