package server

import (
	"encoding/json"
	"errors"
	"log"
	"net/http"

	e "github.com/Amund211/flashlight/internal/errors"
)

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
