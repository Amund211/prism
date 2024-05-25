package server

import (
	"context"
	"net/http"

	"github.com/Amund211/flashlight/internal/logging"
)

type GetMinifiedPlayerData func(ctx context.Context, uuid string) ([]byte, int, error)

func MakeServeGetPlayerData(getMinifiedPlayerData GetMinifiedPlayerData) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		logger := logging.FromContext(r.Context())
		logger.Info("Incoming request")
		uuid := r.URL.Query().Get("uuid")

		minifiedPlayerData, statusCode, err := getMinifiedPlayerData(r.Context(), uuid)

		if err != nil {
			logger.Error("Error getting player data", "error", err)
			writeErrorResponse(r.Context(), w, err)
			return
		}

		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(statusCode)
		w.Write(minifiedPlayerData)
	}
}
