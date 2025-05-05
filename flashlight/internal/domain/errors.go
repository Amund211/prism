package domain

import "errors"

var (
	ErrPlayerNotFound         = errors.New("player not found")
	ErrTemporarilyUnavailable = errors.New("temporarily unavailable")
)
