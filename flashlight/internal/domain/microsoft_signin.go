package domain

import (
	"errors"
	"time"
)

// MicrosoftSignInFlow is one sign-in in progress. It lives in the browser's
// signed flow cookie between /start and /callback, and nowhere else.
type MicrosoftSignInFlow struct {
	// State is the OAuth state sent to Microsoft.
	State string
	// Verifier is the PKCE verifier toward Microsoft.
	Verifier  string
	ExpiresAt time.Time
}

// Why a callback was refused before the code was redeemed.
var (
	ErrMicrosoftSignInFlowMissing   = errors.New("microsoft sign-in flow cookie is missing")
	ErrMicrosoftSignInFlowInvalid   = errors.New("microsoft sign-in flow cookie is invalid")
	ErrMicrosoftSignInFlowExpired   = errors.New("microsoft sign-in flow has expired")
	ErrMicrosoftSignInStateMismatch = errors.New("microsoft sign-in state does not match the flow")
)

// MinecraftAccount is who a Microsoft sign-in proved the caller to be: the
// profile Mojang returned for the token the sign-in obtained. UUID is the
// identity key.
type MinecraftAccount struct {
	UUID     string
	Username string
}

// Expected outcomes of a Microsoft sign-in, one per leg of the chain that can
// refuse a real user. Anything else a leg returns is unexpected.
var (
	// ErrMicrosoftCodeRejected: the token endpoint refused the code
	// (invalid_grant) — expired, already redeemed, or the PKCE verifier does
	// not match.
	ErrMicrosoftCodeRejected = errors.New("microsoft rejected the authorization code")
	// ErrXbox: Xbox Live refused the user or XSTS token for a reason with no
	// entry of its own below.
	ErrXbox = errors.New("xbox live refused the sign-in")
	// ErrNoXboxAccount: the Microsoft account has no Xbox profile (XErr
	// 2148916233).
	ErrNoXboxAccount = errors.New("microsoft account has no xbox account")
	// ErrXboxUnavailableInRegion: XErr 2148916235.
	ErrXboxUnavailableInRegion = errors.New("xbox live is unavailable in the account's region")
	// ErrAdultVerificationRequired: XErr 2148916236 and 2148916237.
	ErrAdultVerificationRequired = errors.New("xbox account needs adult verification")
	// ErrChildAccount: the account must be added to a family by an adult
	// (XErr 2148916238).
	ErrChildAccount = errors.New("xbox account is a child account")
	// ErrClientNotApproved: login_with_xbox answered 403. Expected for every
	// sign-in until Mojang allowlists the Azure client ID.
	ErrClientNotApproved = errors.New("mojang has not approved the azure client id")
	// ErrNoGame: the account does not own Minecraft: Java Edition.
	ErrNoGame = errors.New("account does not own minecraft")
	// ErrNoProfile: the account owns the game but has never created a
	// profile (no username yet).
	ErrNoProfile = errors.New("account has no minecraft profile")
)
