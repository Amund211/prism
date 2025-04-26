package ports

import (
	"context"
	"fmt"
	"net/http"

	"github.com/Amund211/flashlight/internal/adapters/playerprovider"
	"github.com/Amund211/flashlight/internal/domain"
	e "github.com/Amund211/flashlight/internal/errors"
	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/reporting"
)

type GetProcessedPlayerData = func(ctx context.Context, uuid string) (*domain.PlayerPIT, error)

func MakeGetPlayerDataHandler(getProcessedPlayerData GetProcessedPlayerData) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		ctx := r.Context()
		logger := logging.FromContext(ctx)
		uuid := r.URL.Query().Get("uuid")

		player, err := getProcessedPlayerData(r.Context(), uuid)

		if err != nil {
			logger.Error("Error getting player data", "error", err)
			statusCode := writeErrorResponse(r.Context(), w, err)
			logger.Info("Returning response", "statusCode", statusCode, "reason", "error")
			return
		}

		apiResponseFromDomain := playerprovider.DomainPlayerToHypixelAPIResponse(player)

		minifiedPlayerData, err := playerprovider.MarshalPlayerData(ctx, apiResponseFromDomain)
		if err != nil {
			logger.Error("Failed to marshal player data", "error", err)

			err = fmt.Errorf("%w: failed to marshal player data: %w", e.APIServerError, err)
			reporting.Report(ctx, err)

			statusCode := writeErrorResponse(r.Context(), w, err)
			logger.Info("Returning response", "statusCode", statusCode, "reason", "error")
			return
		}

		statusCode := 200
		logger.Info("Got minified player data", "contentLength", len(minifiedPlayerData), "statusCode", 200)

		logger.Info("Returning response", "statusCode", statusCode, "reason", "success")
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(statusCode)
		w.Write(minifiedPlayerData)
	}
}
