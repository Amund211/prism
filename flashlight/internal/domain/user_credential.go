package domain

import (
	"errors"
	"time"
)

// UserCredentialHashLength is the length of a sha256 digest.
const UserCredentialHashLength = 32

var (
	ErrUserCredentialNotFound = errors.New("user credential not found")
	// ErrUserCredentialStale is a known credential past its expiry, most
	// often one rotated out more than a grace window ago. That is the theft
	// signal rotation exists to produce, or a client that lost its write.
	ErrUserCredentialStale = errors.New("user credential is stale")
	// ErrUserCredentialClientMismatch is a credential presented the other
	// client's way, e.g. rainbow's HttpOnly cookie in a request body.
	ErrUserCredentialClientMismatch = errors.New("user credential presented by the wrong client")
)

// UserCredential is one Microsoft-tier recovery credential. Only its hash
// is stored; the value is rainbow's fl_rm cookie or prism's stored
// credential. One identity may hold many.
type UserCredential struct {
	Hash []byte
	// IdentityKey is the verified Minecraft UUID, without dashes.
	IdentityKey string
	// ClientType is for the active-sign-ins view; nothing in recovery
	// reads it.
	ClientType MicrosoftClientType
	// CreatedAt is when the Microsoft sign-in happened.
	CreatedAt time.Time
	ExpiresAt time.Time
}
