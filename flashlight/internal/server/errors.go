package server

import (
	"encoding/json"
	"errors"
	"log"
	"net/http"

	e "github.com/Amund211/flashlight/internal/errors"
)

func writeErrorResponse(w http.ResponseWriter, responseError error) {
	w.Header().Set("Content-Type", "application/json")

	errorResponse := HypixelAPIErrorResponse{
		Success: false,
		Cause:   responseError.Error(),
	}
	errorBytes, err := json.Marshal(errorResponse)
	if err != nil {
		log.Println("Error marshalling error response: %w", err)
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
	}

	w.WriteHeader(statusCode)
	w.Write(errorBytes)
}
