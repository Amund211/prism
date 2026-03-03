package ports

import (
	"fmt"
	"net/http"
)

const (
	missingUserID = "<missing>"
	shortUserID   = "<short-user-id>"
)

// UserID represents a user identifier extracted from an HTTP request.
type UserID string

// String returns the full user ID string.
// Returns "<missing>" for empty user IDs.
func (u UserID) String() string {
	if len(u) == 0 {
		return missingUserID
	}
	return string(u)
}

// LowCardinalityString returns a low cardinality representation of the user ID.
// Returns "<missing>" for empty user IDs.
// For IDs shorter than 20 characters, it returns "<short-user-id>".
// Otherwise, it returns the full user ID (which is truncated to a maximum of 50 characters).
func (u UserID) LowCardinalityString() string {
	if len(u) == 0 {
		return missingUserID
	}
	if len(u) < 20 {
		return shortUserID
	}
	return string(u)
}

func GetUserID(r *http.Request) UserID {
	userID := r.Header.Get("X-User-Id")
	return UserID(fmt.Sprintf("%.50s", userID))
}
