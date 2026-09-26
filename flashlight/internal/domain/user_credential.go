package domain

import "time"

// UserCredentialHashLength is the length of a sha256 digest.
const UserCredentialHashLength = 32

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
