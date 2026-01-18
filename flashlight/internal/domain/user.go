package domain

import (
	"time"
)

type User struct {
	UserID      string
	FirstSeenAt time.Time
	LastSeenAt  time.Time
	SeenCount   int64
}
