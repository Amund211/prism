package server

import (
	"context"
	"net/http"

	"github.com/Amund211/flashlight/internal/logging"
)

type GetProcessedPlayerData func(ctx context.Context, uuid string) ([]byte, int, error)

func MakeGetPlayerDataHandler(getProcessedPlayerData GetProcessedPlayerData) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		logger := logging.FromContext(r.Context())
		uuid := r.URL.Query().Get("uuid")

		playerData, statusCode, err := getProcessedPlayerData(r.Context(), uuid)

		if err != nil {
			logger.Error("Error getting player data", "error", err)
			statusCode := writeErrorResponse(r.Context(), w, err)
			logger.Info("Returning response", "statusCode", statusCode, "reason", "error")
			return
		}

		logger.Info("Returning response", "statusCode", statusCode, "reason", "success")
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(statusCode)
		w.Write(playerData)
	}
}
