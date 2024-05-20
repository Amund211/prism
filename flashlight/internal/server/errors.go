package server

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"

	e "github.com/Amund211/flashlight/internal/errors"
	"github.com/Amund211/flashlight/internal/logging"
)

func writeErrorResponse(ctx context.Context, w http.ResponseWriter, responseError error) {
	w.Header().Set("Content-Type", "application/json")

	errorResponse := HypixelAPIErrorResponse{
		Success: false,
		Cause:   responseError.Error(),
	}
	errorBytes, err := json.Marshal(errorResponse)
	if err != nil {
		logging.FromContext(ctx).Error("Failed to marshal error response", "error", err)
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte(`{"success":false,"cause":"Internal server error (flashlight)"}`))
		return
	}

	// Unknown error: default to 500
	statusCode := http.StatusInternalServerError

	if errors.Is(responseError, e.APIServerError) {
		statusCode = http.StatusInternalServerError
	} else if errors.Is(responseError, e.APIClientError) {
		statusCode = http.StatusBadRequest
	} else if errors.Is(responseError, e.RatelimitExceededError) {
		statusCode = http.StatusTooManyRequests
	} else if errors.Is(responseError, e.BadGateway) {
		statusCode = http.StatusBadGateway
	} else if errors.Is(responseError, e.ServiceUnavailable) {
		statusCode = http.StatusServiceUnavailable
	} else if errors.Is(responseError, e.GatewayTimeout) {
		statusCode = http.StatusGatewayTimeout
	}

	w.WriteHeader(statusCode)
	w.Write(errorBytes)
}
