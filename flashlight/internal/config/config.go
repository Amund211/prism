package config

import (
	"errors"
	"fmt"
	"os"
	"strings"
)

var ErrMissingRequiredValue = errors.New("missing required value")
var ErrInvalidValue = errors.New("invalid value")

type environment string

const (
	production  environment = "production"
	staging     environment = "staging"
	development environment = "development"
)

type Config struct {
	cloudSQLUnixSocketPath string
	dBPassword             string
	dBUsername             string
	sentryDSN              string
	hypixelAPIKey          string
	urchinAPIKey           string
	port                   string
	env                    environment
	blockedIPs             []string
	blockedUserAgents      []string
	blockedUserIDs         []string
	blockedIPsSHA256Hex    []string
	// authChallengeSigningKeys are the HMAC keys for the anonymous-login
	// proof-of-work challenges, newline-delimited and base64-encoded. The
	// first one signs; the rest are still accepted, which is how a key is
	// rotated without invalidating outstanding challenges. Secret.
	authChallengeSigningKeys []string
	// authSessionSigningKeys are the HMAC keys for stateless auth session
	// handles, same format as the challenge keys. A separate list on
	// purpose: two signed blobs that differ only by shape are one refactor
	// away from cross-protocol confusion. Nothing signs with these yet —
	// the sealer arrives with the stateless session cutover. Secret.
	authSessionSigningKeys []string
}

func (c *Config) CloudSQLUnixSocketPath() string {
	return c.cloudSQLUnixSocketPath
}

func (c *Config) DBPassword() string {
	return c.dBPassword
}

func (c *Config) DBUsername() string {
	return c.dBUsername
}

func (c *Config) SentryDSN() string {
	return c.sentryDSN
}

func (c *Config) HypixelAPIKey() string {
	return c.hypixelAPIKey
}

func (c *Config) UrchinAPIKey() string {
	return c.urchinAPIKey
}

func (c *Config) Port() string {
	return c.port
}

func (c *Config) IsProduction() bool {
	return c.env == production
}

func (c *Config) IsStaging() bool {
	return c.env == staging
}

func (c *Config) IsDevelopment() bool {
	return c.env == development
}

func (c *Config) BlockedIPs() []string {
	return c.blockedIPs
}

func (c *Config) BlockedUserAgents() []string {
	return c.blockedUserAgents
}

func (c *Config) BlockedUserIDs() []string {
	return c.blockedUserIDs
}

func (c *Config) BlockedIPsSHA256Hex() []string {
	return c.blockedIPsSHA256Hex
}

func (c *Config) AuthChallengeSigningKeys() []string {
	return c.authChallengeSigningKeys
}

func (c *Config) AuthSessionSigningKeys() []string {
	return c.authSessionSigningKeys
}

// Return a string representation suitable for logging etc
func (c *Config) NonSensitiveString() string {
	return fmt.Sprintf("Config{env: %s, port: %s ...}", string(c.env), c.port)
}

func ConfigFromEnv() (Config, error) {
	missingKey := func(key string) (Config, error) {
		return Config{}, fmt.Errorf("%w: %s", ErrMissingRequiredValue, key)
	}

	var env environment
	rawEnv, ok := os.LookupEnv("FLASHLIGHT_ENVIRONMENT")
	if !ok {
		return missingKey("FLASHLIGHT_ENVIRONMENT")
	}
	switch rawEnv {
	case "production":
		env = production
	case "staging":
		env = staging
	case "development":
		env = development
	default:
		return Config{}, fmt.Errorf("%w: FLASHLIGHT_ENVIRONMENT (%s)", ErrInvalidValue, rawEnv)
	}
	if string(env) == "" {
		panic("logic error: env is empty")
	}

	requireEnv := env == production || env == staging

	cloudSQLUnixSocketPath := os.Getenv("CLOUDSQL_UNIX_SOCKET")
	dbPassword := os.Getenv("DB_PASSWORD")
	dbUsername := os.Getenv("DB_USERNAME")
	sentryDSN := os.Getenv("SENTRY_DSN")
	hypixelAPIKey := os.Getenv("HYPIXEL_API_KEY")
	urchinAPIKey := os.Getenv("URCHIN_API_KEY")

	port := "8080"
	rawPort, ok := os.LookupEnv("PORT")
	if ok {
		port = rawPort
	}

	if env == production || env == staging {
		if cloudSQLUnixSocketPath == "" {
			return missingKey("CLOUDSQL_UNIX_SOCKET")
		}
		if dbUsername == "" {
			return missingKey("DB_USERNAME")
		}
		if dbPassword == "" {
			return missingKey("DB_PASSWORD")
		}
		if sentryDSN == "" {
			return missingKey("SENTRY_DSN")
		}
		if hypixelAPIKey == "" {
			return missingKey("HYPIXEL_API_KEY")
		}
		if urchinAPIKey == "" {
			return missingKey("URCHIN_API_KEY")
		}
	}

	blockedIPs, ok := lookupNewlineDelimitedEnv("BLOCKED_IPS")
	if requireEnv && !ok {
		return missingKey("BLOCKED_IPS")
	}
	blockedUserAgents, ok := lookupNewlineDelimitedEnv("BLOCKED_USER_AGENTS")
	if requireEnv && !ok {
		return missingKey("BLOCKED_USER_AGENTS")
	}
	blockedUserIDs, ok := lookupNewlineDelimitedEnv("BLOCKED_USER_IDS")
	if requireEnv && !ok {
		return missingKey("BLOCKED_USER_IDS")
	}
	blockedIPsSHA256Hex, ok := lookupNewlineDelimitedEnv("BLOCKED_IPS_SHA256_HEX")
	if requireEnv && !ok {
		return missingKey("BLOCKED_IPS_SHA256_HEX")
	}
	// Development runs without it and generates an ephemeral key at
	// startup; production and staging must not, since a key that dies with
	// the process invalidates every outstanding challenge on each revision.
	//
	// Checked on length rather than the ok flag the blocklists use: a
	// secret version rotated to an empty value is *set*, so ok is true, and
	// an empty list is what sends main.go down the ephemeral-key path. The
	// blocklists are legitimately empty; a signing key never is.
	// Whitespace variants included: lookupNewlineDelimitedEnv drops blank
	// entries, so "\n" is an empty list here rather than a list of blanks.
	authChallengeSigningKeys, _ := lookupNewlineDelimitedEnv("AUTH_CHALLENGE_SIGNING_KEYS")
	if requireEnv && len(authChallengeSigningKeys) == 0 {
		return missingKey("AUTH_CHALLENGE_SIGNING_KEYS")
	}
	// Same shape and the same empty-value trap as the challenge keys above.
	// The cost of an ephemeral key is larger here, though: it invalidates
	// every session on restart, against 24h refresh chains, rather than a
	// 60s challenge window. What development does about that is decided
	// when the sealer is wired up.
	authSessionSigningKeys, _ := lookupNewlineDelimitedEnv("AUTH_SESSION_SIGNING_KEYS")
	if requireEnv && len(authSessionSigningKeys) == 0 {
		return missingKey("AUTH_SESSION_SIGNING_KEYS")
	}

	return Config{
		cloudSQLUnixSocketPath: cloudSQLUnixSocketPath,
		dBPassword:             dbPassword,
		dBUsername:             dbUsername,
		sentryDSN:              sentryDSN,
		hypixelAPIKey:          hypixelAPIKey,
		urchinAPIKey:           urchinAPIKey,
		port:                   port,
		env:                    env,
		blockedIPs:             blockedIPs,
		blockedUserAgents:      blockedUserAgents,
		blockedUserIDs:         blockedUserIDs,
		blockedIPsSHA256Hex:    blockedIPsSHA256Hex,

		authChallengeSigningKeys: authChallengeSigningKeys,
		authSessionSigningKeys:   authSessionSigningKeys,
	}, nil
}

func lookupNewlineDelimitedEnv(key string) ([]string, bool) {
	value, ok := os.LookupEnv(key)
	if !ok {
		return []string{}, false
	}

	if value == "" {
		return []string{}, true
	}

	// Entries that are empty once trimmed are dropped. A trailing newline or a
	// comment-only line is routine in a hand-edited secret, and a blank entry
	// is matched with slices.Contains like any other — so keeping it blocks
	// every request whose user agent or user id is absent.
	parts := make([]string, 0, strings.Count(value, "\n")+1)
	for part := range strings.SplitSeq(value, "\n") {
		// Strip comment (everything from the first # onwards)
		if hashIndex := strings.Index(part, "#"); hashIndex != -1 {
			part = part[:hashIndex]
		}
		part = strings.TrimSpace(part)
		if part == "" {
			continue
		}
		parts = append(parts, part)
	}

	return parts, true
}
