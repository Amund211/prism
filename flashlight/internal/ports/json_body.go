package ports

import (
	"encoding/json/v2"
	"errors"
	"net/http"

	"github.com/Amund211/prism/flashlight/internal/logging"
)

// decodeJSONBody decodes the request body into out. On failure it returns
// the status to answer with: 413 for an oversized body, else 400.
func decodeJSONBody(w http.ResponseWriter, r *http.Request, maxBytes int64, out any) (int, error) {
	err := json.UnmarshalRead(http.MaxBytesReader(w, r.Body, maxBytes), out)
	if err == nil {
		return http.StatusOK, nil
	}
	if _, ok := errors.AsType[*http.MaxBytesError](err); ok {
		return http.StatusRequestEntityTooLarge, err
	}
	return http.StatusBadRequest, err
}

// readJSONBody is decodeJSONBody with a plain-text error response. It
// returns false when it has already answered the request.
func readJSONBody(w http.ResponseWriter, r *http.Request, maxBytes int64, out any) bool {
	status, err := decodeJSONBody(w, r, maxBytes, out)
	if err == nil {
		return true
	}

	if status == http.StatusRequestEntityTooLarge {
		http.Error(w, "Request body too large", status)
		return false
	}

	ctx := r.Context()
	logging.FromContext(ctx).WarnContext(ctx, "Failed to parse request body", "error", err)
	http.Error(w, "Failed to parse request body", status)
	return false
}
