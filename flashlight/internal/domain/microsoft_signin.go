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
	// Target is nil for the test sign-in, which renders a page instead.
	Target *MicrosoftSignInTarget
}

// MicrosoftClientType is the client a sign-in returns to.
type MicrosoftClientType string

const (
	MicrosoftClientRainbow MicrosoftClientType = "rainbow"
	MicrosoftClientPrism   MicrosoftClientType = "prism"
)

func (c MicrosoftClientType) IsKnown() bool {
	return c == MicrosoftClientRainbow || c == MicrosoftClientPrism
}

// Bounds on the client-supplied parts of a target, so the flow cookie
// stays under its cap.
const (
	MicrosoftSignInReturnMaxLength      = 256
	MicrosoftSignInClientStateMaxLength = 128
)

// MicrosoftSignInTarget is where the callback sends the result token, and
// what the client must prove at /exchange.
type MicrosoftSignInTarget struct {
	ClientType MicrosoftClientType
	// URL is the validated return: a rainbow origin or a prism loopback
	// callback.
	URL string
	// Challenge is base64url(sha256(verifier)); the client holds the
	// verifier.
	Challenge string
	// ClientState is prism's loopback nonce, echoed back unchecked.
	ClientState string
}

// Complete reports whether every required field is set.
func (t MicrosoftSignInTarget) Complete() bool {
	return t.ClientType.IsKnown() && t.URL != "" && t.Challenge != ""
}

// MicrosoftSignInResult is what the callback hands the client, signed, for
// it to trade at /exchange together with the verifier.
type MicrosoftSignInResult struct {
	Account    MinecraftAccount
	ClientType MicrosoftClientType
	Challenge  string
	ExpiresAt  time.Time
}

// Why a callback was refused before the code was redeemed.
var (
	ErrMicrosoftSignInFlowMissing   = errors.New("microsoft sign-in flow cookie is missing")
	ErrMicrosoftSignInFlowInvalid   = errors.New("microsoft sign-in flow cookie is invalid")
	ErrMicrosoftSignInFlowExpired   = errors.New("microsoft sign-in flow has expired")
	ErrMicrosoftSignInStateMismatch = errors.New("microsoft sign-in state does not match the flow")
	// ErrMicrosoftSignInRefused: Microsoft redirected back with an error,
	// not a code.
	ErrMicrosoftSignInRefused = errors.New("microsoft refused the sign-in")
)

// Why /exchange refused a result token.
var (
	// ErrMicrosoftSignInResultInvalid is every refusal of a result token
	// we did not sign or cannot read.
	ErrMicrosoftSignInResultInvalid    = errors.New("microsoft sign-in result is invalid")
	ErrMicrosoftSignInResultExpired    = errors.New("microsoft sign-in result has expired")
	ErrMicrosoftSignInVerifierMismatch = errors.New("verifier does not match the sign-in challenge")
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
