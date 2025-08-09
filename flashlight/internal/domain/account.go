package domain

import "time"

type Account struct {
	UUID      string
	Username  string
	QueriedAt time.Time
}
