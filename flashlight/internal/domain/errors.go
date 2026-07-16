package domain

import "errors"

var (
	ErrInvalidAPIKey          = errors.New("invalid API key")
	ErrPlayerNotFound         = errors.New("player not found")
	ErrTemporarilyUnavailable = errors.New("temporarily unavailable")
	ErrUserNotFound           = errors.New("user not found")
	ErrUsernameNotFound       = errors.New("username not found")
)
