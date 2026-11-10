package microsoftauth

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"strings"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/strutils"
)

// XSTS error codes with an outcome of their own.
// https://minecraft.wiki/w/Microsoft_authentication
var xErrOutcomes = map[int64]error{
	2148916233: domain.ErrNoXboxAccount,
	2148916235: domain.ErrXboxUnavailableInRegion,
	2148916236: domain.ErrAdultVerificationRequired,
	2148916237: domain.ErrAdultVerificationRequired,
	2148916238: domain.ErrChildAccount,
}

func (c *Client) redeemCode(ctx context.Context, code, codeVerifier string) (secret, error) {
	const leg = "redeem code"
	ctx, span := c.tracer.Start(ctx, "microsoftauth.redeemCode")
	defer span.End()

	form := url.Values{
		"client_id":     {c.config.ClientID},
		"client_secret": {c.config.ClientSecret},
		"grant_type":    {"authorization_code"},
		"code":          {code},
		"redirect_uri":  {c.config.RedirectURI},
		"code_verifier": {codeVerifier},
		"scope":         {scope},
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.config.Endpoints.Token, strings.NewReader(form.Encode()))
	if err != nil {
		return "", fmt.Errorf("%s: failed to create request: %w", leg, err)
	}
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	req.Header.Set("Accept", "application/json")

	status, body, err := c.do(req, leg)
	if err != nil {
		return "", err
	}

	var response struct {
		AccessToken string `json:"access_token"`
		// Error is an OAuth error code such as invalid_grant. The
		// error_description is not read: it may quote the code.
		Error string `json:"error"`
	}
	parseErr := json.Unmarshal(body, &response)

	switch {
	case temporaryStatus(status):
		return "", fmt.Errorf("%w: %s: status %d", domain.ErrTemporarilyUnavailable, leg, status)
	case status != http.StatusOK:
		if response.Error == "invalid_grant" {
			return "", fmt.Errorf("%w: %s: status %d", domain.ErrMicrosoftCodeRejected, leg, status)
		}
		return "", fmt.Errorf("%s: status %d, error %q", leg, status, oauthErrorCode(response.Error))
	case parseErr != nil:
		return "", fmt.Errorf("%s: response is not json", leg)
	case response.AccessToken == "":
		return "", fmt.Errorf("%s: response has no access token", leg)
	}
	return secret(response.AccessToken), nil
}

// oauthErrorCode passes a well-formed OAuth error code through and drops
// anything else, so a body shaped unlike the spec cannot smuggle text into
// an error.
func oauthErrorCode(code string) string {
	if len(code) > 64 {
		return "<invalid>"
	}
	for _, r := range code {
		if (r < 'a' || r > 'z') && r != '_' {
			return "<invalid>"
		}
	}
	return code
}

type xboxResponse struct {
	Token         string `json:"Token"`
	DisplayClaims struct {
		XUI []struct {
			UserHash string `json:"uhs"`
		} `json:"xui"`
	} `json:"DisplayClaims"`
	XErr int64 `json:"XErr"`
}

func (c *Client) postJSON(ctx context.Context, leg, endpoint string, payload any) (int, []byte, error) {
	encoded, err := json.Marshal(payload)
	if err != nil {
		return 0, nil, fmt.Errorf("%s: failed to encode request: %w", leg, err)
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpoint, bytes.NewReader(encoded))
	if err != nil {
		return 0, nil, fmt.Errorf("%s: failed to create request: %w", leg, err)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Accept", "application/json")
	return c.do(req, leg)
}

func (c *Client) authenticateXbox(ctx context.Context, microsoftToken secret) (secret, error) {
	const leg = "xbox user token"
	ctx, span := c.tracer.Start(ctx, "microsoftauth.authenticateXbox")
	defer span.End()

	status, body, err := c.postJSON(ctx, leg, c.config.Endpoints.XboxUser, map[string]any{
		"Properties": map[string]any{
			"AuthMethod": "RPS",
			"SiteName":   "user.auth.xboxlive.com",
			"RpsTicket":  "d=" + microsoftToken.reveal(),
		},
		"RelyingParty": "http://auth.xboxlive.com",
		"TokenType":    "JWT",
	})
	if err != nil {
		return "", err
	}

	switch {
	case temporaryStatus(status):
		return "", fmt.Errorf("%w: %s: status %d", domain.ErrTemporarilyUnavailable, leg, status)
	case status != http.StatusOK:
		return "", fmt.Errorf("%w: %s: status %d", domain.ErrXbox, leg, status)
	}

	var response xboxResponse
	if err := json.Unmarshal(body, &response); err != nil {
		return "", fmt.Errorf("%s: response is not json", leg)
	}
	if response.Token == "" {
		return "", fmt.Errorf("%s: response has no token", leg)
	}
	return secret(response.Token), nil
}

// authorizeXSTS returns the XSTS token and the user hash login_with_xbox
// needs alongside it.
func (c *Client) authorizeXSTS(ctx context.Context, xboxToken secret) (secret, string, error) {
	const leg = "xsts token"
	ctx, span := c.tracer.Start(ctx, "microsoftauth.authorizeXSTS")
	defer span.End()

	status, body, err := c.postJSON(ctx, leg, c.config.Endpoints.XSTS, map[string]any{
		"Properties": map[string]any{
			"SandboxId":  "RETAIL",
			"UserTokens": []string{xboxToken.reveal()},
		},
		"RelyingParty": "rp://api.minecraftservices.com/",
		"TokenType":    "JWT",
	})
	if err != nil {
		return "", "", err
	}

	var response xboxResponse
	parseErr := json.Unmarshal(body, &response)

	switch {
	case temporaryStatus(status):
		return "", "", fmt.Errorf("%w: %s: status %d", domain.ErrTemporarilyUnavailable, leg, status)
	case status != http.StatusOK:
		if outcome, ok := xErrOutcomes[response.XErr]; ok {
			return "", "", fmt.Errorf("%w: %s: XErr %d", outcome, leg, response.XErr)
		}
		return "", "", fmt.Errorf("%w: %s: status %d, XErr %d", domain.ErrXbox, leg, status, response.XErr)
	case parseErr != nil:
		return "", "", fmt.Errorf("%s: response is not json", leg)
	case response.Token == "":
		return "", "", fmt.Errorf("%s: response has no token", leg)
	case len(response.DisplayClaims.XUI) == 0 || response.DisplayClaims.XUI[0].UserHash == "":
		return "", "", fmt.Errorf("%s: response has no user hash", leg)
	}
	return secret(response.Token), response.DisplayClaims.XUI[0].UserHash, nil
}

func (c *Client) loginWithXbox(ctx context.Context, xstsToken secret, userHash string) (secret, error) {
	const leg = "minecraft token"
	ctx, span := c.tracer.Start(ctx, "microsoftauth.loginWithXbox")
	defer span.End()

	status, body, err := c.postJSON(ctx, leg, c.config.Endpoints.LoginWithXbox, map[string]string{
		"identityToken": "XBL3.0 x=" + userHash + ";" + xstsToken.reveal(),
	})
	if err != nil {
		return "", err
	}

	switch {
	case status == http.StatusForbidden:
		return "", fmt.Errorf("%w: %s: status %d", domain.ErrClientNotApproved, leg, status)
	case temporaryStatus(status):
		return "", fmt.Errorf("%w: %s: status %d", domain.ErrTemporarilyUnavailable, leg, status)
	case status != http.StatusOK:
		return "", fmt.Errorf("%s: status %d", leg, status)
	}

	var response struct {
		AccessToken string `json:"access_token"`
	}
	if err := json.Unmarshal(body, &response); err != nil {
		return "", fmt.Errorf("%s: response is not json", leg)
	}
	if response.AccessToken == "" {
		return "", fmt.Errorf("%s: response has no access token", leg)
	}
	return secret(response.AccessToken), nil
}

func (c *Client) getWithBearer(ctx context.Context, leg, endpoint string, token secret) (int, []byte, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, endpoint, http.NoBody)
	if err != nil {
		return 0, nil, fmt.Errorf("%s: failed to create request: %w", leg, err)
	}
	req.Header.Set("Authorization", "Bearer "+token.reveal())
	req.Header.Set("Accept", "application/json")
	return c.do(req, leg)
}

func (c *Client) checkOwnership(ctx context.Context, minecraftToken secret) error {
	const leg = "ownership"
	ctx, span := c.tracer.Start(ctx, "microsoftauth.checkOwnership")
	defer span.End()

	status, body, err := c.getWithBearer(ctx, leg, c.config.Endpoints.Entitlements, minecraftToken)
	if err != nil {
		return err
	}

	switch {
	case temporaryStatus(status):
		return fmt.Errorf("%w: %s: status %d", domain.ErrTemporarilyUnavailable, leg, status)
	case status != http.StatusOK:
		return fmt.Errorf("%s: status %d", leg, status)
	}

	var response struct {
		Items []struct {
			Name string `json:"name"`
		} `json:"items"`
	}
	if err := json.Unmarshal(body, &response); err != nil {
		return fmt.Errorf("%s: response is not json", leg)
	}
	for _, item := range response.Items {
		if item.Name == "game_minecraft" || item.Name == "product_minecraft" {
			return nil
		}
	}
	return fmt.Errorf("%w: %s", domain.ErrNoGame, leg)
}

func (c *Client) getProfile(ctx context.Context, minecraftToken secret) (domain.MinecraftAccount, error) {
	const leg = "profile"
	ctx, span := c.tracer.Start(ctx, "microsoftauth.getProfile")
	defer span.End()

	status, body, err := c.getWithBearer(ctx, leg, c.config.Endpoints.Profile, minecraftToken)
	if err != nil {
		return domain.MinecraftAccount{}, err
	}

	switch {
	case status == http.StatusNotFound:
		return domain.MinecraftAccount{}, fmt.Errorf("%w: %s", domain.ErrNoProfile, leg)
	case temporaryStatus(status):
		return domain.MinecraftAccount{}, fmt.Errorf("%w: %s: status %d", domain.ErrTemporarilyUnavailable, leg, status)
	case status != http.StatusOK:
		return domain.MinecraftAccount{}, fmt.Errorf("%s: status %d", leg, status)
	}

	var response struct {
		ID   string `json:"id"`
		Name string `json:"name"`
	}
	if err := json.Unmarshal(body, &response); err != nil {
		return domain.MinecraftAccount{}, fmt.Errorf("%s: response is not json", leg)
	}
	uuid, err := strutils.NormalizeUUID(response.ID)
	if err != nil {
		return domain.MinecraftAccount{}, errors.New(leg + ": response has an invalid uuid")
	}
	if response.Name == "" {
		return domain.MinecraftAccount{}, fmt.Errorf("%s: response has no name", leg)
	}
	return domain.MinecraftAccount{UUID: uuid, Username: response.Name}, nil
}
