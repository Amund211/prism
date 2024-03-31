package server

import (
	"context"
	"log"
	"net/http"

	"github.com/Amund211/flashlight/internal/reporting"
)

type GetMinifiedPlayerData func(ctx context.Context, uuid string) ([]byte, int, error)

func MakeServeGetPlayerData(getMinifiedPlayerData GetMinifiedPlayerData) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		log.Println("Incoming request")
		uuid := r.URL.Query().Get("uuid")

		minifiedPlayerData, statusCode, err := getMinifiedPlayerData(r.Context(), uuid)

		if err != nil {
			log.Println("Error getting player data:", err)
			reporting.Report(r.Context(), err, nil, nil)
			writeErrorResponse(w, err)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(statusCode)
		w.Write(minifiedPlayerData)
	}
}
