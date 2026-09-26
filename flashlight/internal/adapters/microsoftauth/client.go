// Package microsoftauth runs the Microsoft → Xbox → Minecraft sign-in chain
// for a code Microsoft issued to flashlight's Entra app.
//
// No token leaves this package, and no error it returns quotes a token, a
// code, the client secret or a response body, so its errors are safe to log
// and report. It reports nothing itself: most failures are expected outcomes
// for a real user, and the caller knows which.
package microsoftauth

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"

	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/trace"

	"github.com/Amund211/flashlight/internal/constants"
	"github.com/Amund211/flashlight/internal/domain"
)

// scope is the only scope requested. Never offline_access: without it no
// refresh token is issued, so none can leak.
const scope = "XboxLive.signin"

// maxResponseBytes bounds each response read. The largest real one, the
// entitlements list, is a few KB.
const maxResponseBytes = 1 << 20

// Endpoints are the URLs of each leg. Tests point them at a fake.
type Endpoints struct {
	Authorize     string
	Token         string
	XboxUser      string
	XSTS          string
	LoginWithXbox string
	Entitlements  string
	Profile       string
}

func DefaultEndpoints() Endpoints {
	return Endpoints{
		Authorize:     "https://login.microsoftonline.com/consumers/oauth2/v2.0/authorize",
		Token:         "https://login.microsoftonline.com/consumers/oauth2/v2.0/token",
		XboxUser:      "https://user.auth.xboxlive.com/user/authenticate",
		XSTS:          "https://xsts.auth.xboxlive.com/xsts/authorize",
		LoginWithXbox: "https://api.minecraftservices.com/authentication/login_with_xbox",
		Entitlements:  "https://api.minecraftservices.com/entitlements/mcstore",
		Profile:       "https://api.minecraftservices.com/minecraft/profile",
	}
}

// Config is the Entra app registration plus where each leg is served.
type Config struct {
	ClientID     string
	ClientSecret string
	// RedirectURI must equal the one registered in Entra byte for byte.
	RedirectURI string
	Endpoints   Endpoints
}

type Client struct {
	httpClient *http.Client
	config     Config
	tracer     trace.Tracer
}

// New uses a copy of httpClient that never follows a redirect: a 307 or 308
// would replay a body holding the client secret, the code or a token to the
// Location host. No leg redirects, so a 3xx is an unexpected status.
func New(httpClient *http.Client, config Config) (*Client, error) {
	switch {
	case httpClient == nil:
		return nil, errors.New("microsoftauth: missing http client")
	case config.ClientID == "":
		return nil, errors.New("microsoftauth: missing client id")
	case config.ClientSecret == "":
		return nil, errors.New("microsoftauth: missing client secret")
	case config.RedirectURI == "":
		return nil, errors.New("microsoftauth: missing redirect uri")
	}
	e := config.Endpoints
	for _, endpoint := range []string{e.Authorize, e.Token, e.XboxUser, e.XSTS, e.LoginWithXbox, e.Entitlements, e.Profile} {
		if endpoint == "" {
			return nil, errors.New("microsoftauth: missing endpoint")
		}
	}

	noRedirects := *httpClient
	noRedirects.CheckRedirect = func(*http.Request, []*http.Request) error {
		return http.ErrUseLastResponse
	}

	return &Client{
		httpClient: &noRedirects,
		config:     config,
		tracer:     otel.Tracer("flashlight/adapters/microsoftauth"),
	}, nil
}

// AuthorizeURL is where /start sends the browser. codeChallenge is the
// base64url SHA-256 of the PKCE verifier that SignIn later receives.
// prompt is left out, so Microsoft may skip the account picker.
func (c *Client) AuthorizeURL(state, codeChallenge string) string {
	query := url.Values{
		"client_id":             {c.config.ClientID},
		"response_type":         {"code"},
		"redirect_uri":          {c.config.RedirectURI},
		"response_mode":         {"query"},
		"scope":                 {scope},
		"state":                 {state},
		"code_challenge":        {codeChallenge},
		"code_challenge_method": {"S256"},
	}
	return c.config.Endpoints.Authorize + "?" + query.Encode()
}

// SignIn redeems code and runs the chain to the Minecraft profile. Every
// token lives only for this call. Errors wrap the domain errors in
// microsoft_signin.go, domain.ErrTemporarilyUnavailable, or neither when the
// failure is unexpected.
func (c *Client) SignIn(ctx context.Context, code, codeVerifier string) (domain.MinecraftAccount, error) {
	ctx, span := c.tracer.Start(ctx, "microsoftauth.SignIn")
	defer span.End()

	microsoftToken, err := c.redeemCode(ctx, code, codeVerifier)
	if err != nil {
		return domain.MinecraftAccount{}, err
	}
	xboxToken, err := c.authenticateXbox(ctx, microsoftToken)
	if err != nil {
		return domain.MinecraftAccount{}, err
	}
	xstsToken, userHash, err := c.authorizeXSTS(ctx, xboxToken)
	if err != nil {
		return domain.MinecraftAccount{}, err
	}
	minecraftToken, err := c.loginWithXbox(ctx, xstsToken, userHash)
	if err != nil {
		return domain.MinecraftAccount{}, err
	}
	if err := c.checkOwnership(ctx, minecraftToken); err != nil {
		return domain.MinecraftAccount{}, err
	}
	return c.getProfile(ctx, minecraftToken)
}

// do sends req and reads the body. The error names the leg and never the
// request body; the URLs carry no secrets.
func (c *Client) do(req *http.Request, leg string) (int, []byte, error) {
	req.Header.Set("User-Agent", constants.UserAgent)
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return 0, nil, fmt.Errorf("%s: failed to send request: %w", leg, err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(io.LimitReader(resp.Body, maxResponseBytes))
	if err != nil {
		return 0, nil, fmt.Errorf("%s: failed to read response body: %w", leg, err)
	}
	return resp.StatusCode, body, nil
}

// temporaryStatus reports the statuses every leg treats as a transient
// outage rather than an answer about the user.
func temporaryStatus(status int) bool {
	return status == http.StatusTooManyRequests || status >= http.StatusInternalServerError
}
