package ports

import (
	"encoding/json/v2"
	"errors"
	"net/http"

	"github.com/Amund211/prism/flashlight/internal/logging"
)

// readJSONBody decodes the request body into out, or writes a 413/400 and
// returns false.
func readJSONBody(w http.ResponseWriter, r *http.Request, maxBytes int64, out any) bool {
	ctx := r.Context()

	err := json.UnmarshalRead(http.MaxBytesReader(w, r.Body, maxBytes), out)
	if err == nil {
		return true
	}

	if _, ok := errors.AsType[*http.MaxBytesError](err); ok {
		http.Error(w, "Request body too large", http.StatusRequestEntityTooLarge)
		return false
	}

	logging.FromContext(ctx).WarnContext(ctx, "Failed to parse request body", "error", err)
	http.Error(w, "Failed to parse request body", http.StatusBadRequest)
	return false
}
