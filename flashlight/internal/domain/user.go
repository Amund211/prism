package domain

import (
	"time"
)

type User struct {
	UserID        string
	FirstSeenAt   time.Time
	LastSeenAt    time.Time
	LastIPHash    string
	LastUserAgent string
	SeenCount     int64
}
