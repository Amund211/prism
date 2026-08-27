package config_test

import (
	"os"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/config"
)

type environment string

const (
	production  environment = "production"
	staging     environment = "staging"
	development environment = "development"
)

var allVariablesExceptEnv = []string{"CLOUDSQL_UNIX_SOCKET", "DB_PASSWORD", "DB_USERNAME", "SENTRY_DSN", "HYPIXEL_API_KEY", "URCHIN_API_KEY", "BLOCKED_IPS", "BLOCKED_USER_AGENTS", "BLOCKED_USER_IDS", "BLOCKED_IPS_SHA256_HEX", "AUTH_CHALLENGE_SIGNING_KEYS", "AUTH_SESSION_SIGNING_KEYS"}

// The two signing key lists behave identically — required in production and
// staging, ordered, blank-entry tolerant — so every property is asserted for
// both. Domain separation means there will never be fewer than two.
var signingKeyLists = []struct {
	envVar string
	get    func(*config.Config) []string
}{
	{"AUTH_CHALLENGE_SIGNING_KEYS", (*config.Config).AuthChallengeSigningKeys},
	{"AUTH_SESSION_SIGNING_KEYS", (*config.Config).AuthSessionSigningKeys},
}

func TestGetConfig(t *testing.T) {
	compareConfig := func(t *testing.T, socketPath, username, password, sentryDSN, hypixelAPIKey, urchinAPIKey string, blockedIPs, blockedUserAgents, blockedUserIDs, blockedIPsSHA256Hex, authChallengeSigningKeys, authSessionSigningKeys []string, env environment, conf config.Config) {
		t.Helper()
		require.Equal(t, socketPath, conf.CloudSQLUnixSocketPath())
		require.Equal(t, username, conf.DBUsername())
		require.Equal(t, password, conf.DBPassword())
		require.Equal(t, sentryDSN, conf.SentryDSN())
		require.Equal(t, hypixelAPIKey, conf.HypixelAPIKey())
		require.Equal(t, urchinAPIKey, conf.UrchinAPIKey())
		require.Equal(t, blockedIPs, conf.BlockedIPs())
		require.Equal(t, blockedUserAgents, conf.BlockedUserAgents())
		require.Equal(t, blockedUserIDs, conf.BlockedUserIDs())
		require.Equal(t, blockedIPsSHA256Hex, conf.BlockedIPsSHA256Hex())
		require.Equal(t, authChallengeSigningKeys, conf.AuthChallengeSigningKeys())
		require.Equal(t, authSessionSigningKeys, conf.AuthSessionSigningKeys())
		require.Equal(t, env == production, conf.IsProduction())
		require.Equal(t, env == staging, conf.IsStaging())
		require.Equal(t, env == development, conf.IsDevelopment())
	}

	t.Run("ensure base environment is clean", func(t *testing.T) {
		t.Run("environment is missing", func(t *testing.T) {
			// FLASHLIGHT_ENVIRONMENT is required, so this should fail
			_, err := config.ConfigFromEnv()
			require.ErrorIs(t, err, config.ErrMissingRequiredValue)
		})

		t.Run("development environment should be empty", func(t *testing.T) {
			t.Setenv("FLASHLIGHT_ENVIRONMENT", "development")

			conf, err := config.ConfigFromEnv()
			require.NoError(t, err)
			compareConfig(t, "", "", "", "", "", "", []string{}, []string{}, []string{}, []string{}, []string{}, []string{}, development, conf)
		})
	})

	t.Run("values are read correctly", func(t *testing.T) {
		for _, variable := range allVariablesExceptEnv {
			t.Setenv(variable, variable)
		}

		for _, env := range []environment{production, staging, development} {
			t.Run(string(env), func(t *testing.T) {
				t.Setenv("FLASHLIGHT_ENVIRONMENT", string(env))

				conf, err := config.ConfigFromEnv()
				require.NoError(t, err)
				compareConfig(t, "CLOUDSQL_UNIX_SOCKET", "DB_USERNAME", "DB_PASSWORD", "SENTRY_DSN", "HYPIXEL_API_KEY", "URCHIN_API_KEY", []string{"BLOCKED_IPS"}, []string{"BLOCKED_USER_AGENTS"}, []string{"BLOCKED_USER_IDS"}, []string{"BLOCKED_IPS_SHA256_HEX"}, []string{"AUTH_CHALLENGE_SIGNING_KEYS"}, []string{"AUTH_SESSION_SIGNING_KEYS"}, env, conf)
			})
		}

		t.Run("no sensitive data in NonSensitiveString", func(t *testing.T) {
			t.Setenv("FLASHLIGHT_ENVIRONMENT", string(production))
			conf, err := config.ConfigFromEnv()
			require.NoError(t, err)

			for _, sensitive := range []string{"DB_PASSWORD", "HYPIXEL_API_KEY", "URCHIN_API_KEY", "SENTRY_DSN", "AUTH_CHALLENGE_SIGNING_KEYS", "AUTH_SESSION_SIGNING_KEYS"} {
				require.NotContains(t, conf.NonSensitiveString(), sensitive)
			}
		})

	})

	t.Run("production and staging fail when missing variables", func(t *testing.T) {
		// Set all variables
		for _, variable := range allVariablesExceptEnv {
			t.Setenv(variable, "placeholder_value")
		}

		for _, env := range []environment{production, staging} {
			t.Run(string(env), func(t *testing.T) {
				t.Setenv("FLASHLIGHT_ENVIRONMENT", string(env))

				for _, variable := range allVariablesExceptEnv {
					t.Run(variable, func(t *testing.T) {
						// Set it here so t.Setenv's own cleanup restores it,
						// then unset it. Restoring by calling t.Setenv *from* a
						// cleanup instead leaves it unset: that registers a
						// further cleanup which promptly reverts to the
						// pre-Setenv value, which is unset. Every subtest after
						// the first then failed on a leaked variable rather
						// than its own, and passed for the wrong reason.
						t.Setenv(variable, "placeholder_value")
						err := os.Unsetenv(variable)
						require.NoError(t, err)

						_, err = config.ConfigFromEnv()
						require.ErrorIs(t, err, config.ErrMissingRequiredValue, "%s must be required", variable)
					})
				}
			})
		}
	})

	t.Run("invalid environment", func(t *testing.T) {
		for _, env := range []string{"", "invalid", "my-env"} {
			t.Run(env, func(t *testing.T) {
				t.Setenv("FLASHLIGHT_ENVIRONMENT", "")
				_, err := config.ConfigFromEnv()
				require.ErrorIs(t, err, config.ErrInvalidValue)
			})
		}
	})

	// A secret version rotated to an empty value is set, so the ok flag the
	// blocklists check is true. Letting that through means main.go sees an
	// empty list and generates an ephemeral key, so production boots green
	// with a per-revision key and rejects every challenge minted by the
	// outgoing revision. For session keys the same mistake logs out every
	// client instead.
	t.Run("production and staging reject an empty signing key list", func(t *testing.T) {
		for _, variable := range allVariablesExceptEnv {
			t.Setenv(variable, "placeholder_value")
		}

		for _, keyList := range signingKeyLists {
			t.Run(keyList.envVar, func(t *testing.T) {
				// Whitespace counts as empty. A secret is a hand-edited value,
				// so "\n" and "   " are the realistic shapes of "rotated to
				// nothing" — and they used to parse as a list of blank entries,
				// which is non-empty, so the check here passed and the failure
				// moved to ParseSigningKeys in another package.
				for name, value := range map[string]string{
					"empty":              "",
					"one newline":        "\n",
					"spaces":             "   ",
					"newlines and tabs":  "\n\t\n  \n",
					"comment only":       "# rotated out, forgot to add the new one",
					"comment and blanks": "\n# nothing here\n   \n",
				} {
					for _, env := range []environment{production, staging} {
						t.Run(name+"/"+string(env), func(t *testing.T) {
							t.Setenv("FLASHLIGHT_ENVIRONMENT", string(env))
							t.Setenv(keyList.envVar, value)

							_, err := config.ConfigFromEnv()
							require.ErrorIs(t, err, config.ErrMissingRequiredValue)
						})
					}

					t.Run(name+"/development still runs without one", func(t *testing.T) {
						t.Setenv("FLASHLIGHT_ENVIRONMENT", string(development))
						t.Setenv(keyList.envVar, value)

						conf, err := config.ConfigFromEnv()
						require.NoError(t, err)
						require.Empty(t, keyList.get(&conf),
							"development runs without a key, which needs an empty list rather than a list of blanks")
					})
				}
			})
		}
	})

	t.Run("signing keys are parsed as an ordered list", func(t *testing.T) {
		for _, variable := range allVariablesExceptEnv {
			t.Setenv(variable, "placeholder_value")
		}
		t.Setenv("FLASHLIGHT_ENVIRONMENT", string(production))

		for _, keyList := range signingKeyLists {
			t.Run(keyList.envVar, func(t *testing.T) {
				t.Setenv(keyList.envVar, "primary\nsecondary")

				conf, err := config.ConfigFromEnv()
				require.NoError(t, err)
				require.Equal(t, []string{"primary", "secondary"}, keyList.get(&conf),
					"the first key signs and the rest are only accepted, so the order is load-bearing for rotation")
			})
		}
	})

	t.Run("blocked IPs, user agents, and user ids are parsed correctly", func(t *testing.T) {
		// Set all variables
		for _, variable := range allVariablesExceptEnv {
			t.Setenv(variable, "placeholder_value")
		}

		cases := []struct {
			name         string
			envValue     string
			expectedList []string
		}{
			{
				name:         "empty value",
				envValue:     "",
				expectedList: []string{},
			},
			{
				name:         "single value",
				envValue:     "singlevalue",
				expectedList: []string{"singlevalue"},
			},
			{
				name: "multiple values",
				envValue: `value1
value2
value3`,
				expectedList: []string{"value1", "value2", "value3"},
			},
			{
				name: "multiple values with spaces",
				envValue: `value1
 value2 
 value3 `,
				expectedList: []string{"value1", "value2", "value3"},
			},
			{
				name:         "value with comment and space before hash",
				envValue:     "value1 # this is a comment",
				expectedList: []string{"value1"},
			},
			{
				name:         "value with comment and no space before hash",
				envValue:     "value1# this is a comment",
				expectedList: []string{"value1"},
			},
			{
				name:         "value with leading and trailing spaces and comment",
				envValue:     "  value1   # comment",
				expectedList: []string{"value1"},
			},
			{
				name:         "multiple values with comments",
				envValue:     "value1 # comment1\nvalue2# comment2\nvalue3 #comment3",
				expectedList: []string{"value1", "value2", "value3"},
			},
			{
				name:         "multiple hashes in line - only first is comment",
				envValue:     "value1 # comment # with # more # hashes",
				expectedList: []string{"value1"},
			},
			{
				// Entries that are empty once the comment is stripped and
				// the rest trimmed are dropped, not kept as empty strings. A
				// blank entry is matched with slices.Contains like any other,
				// so keeping it would block every request whose user agent or
				// user id is absent.
				name:         "line with only comment",
				envValue:     "# this is just a comment",
				expectedList: []string{},
			},
			{
				name:         "mixed lines with and without comments",
				envValue:     "value1\nvalue2 # with comment\nvalue3",
				expectedList: []string{"value1", "value2", "value3"},
			},
			{
				name:         "value with hash but no space before it",
				envValue:     "value#nocomment",
				expectedList: []string{"value"},
			},
			{
				name:         "empty line and line with comment",
				envValue:     "\n# comment\nvalue1",
				expectedList: []string{"value1"},
			},
			{
				name: "complex real-world example",
				envValue: `192.168.1.1 # suspicious IP
192.168.1.2# another one
192.168.1.3
  192.168.1.4  # IP with spaces
# 192.168.1.5 commented out IP
192.168.1.6 # comment with # multiple # hashes`,
				expectedList: []string{"192.168.1.1", "192.168.1.2", "192.168.1.3", "192.168.1.4", "192.168.1.6"},
			},
		}

		for _, c := range cases {
			t.Run(c.name, func(t *testing.T) {
				t.Setenv("FLASHLIGHT_ENVIRONMENT", string(production))
				t.Setenv("BLOCKED_IPS", c.envValue)
				t.Setenv("BLOCKED_USER_AGENTS", c.envValue)
				t.Setenv("BLOCKED_USER_IDS", c.envValue)
				t.Setenv("BLOCKED_IPS_SHA256_HEX", c.envValue)

				conf, err := config.ConfigFromEnv()
				require.NoError(t, err)
				require.Equal(t, c.expectedList, conf.BlockedIPs())
				require.Equal(t, c.expectedList, conf.BlockedUserAgents())
				require.Equal(t, c.expectedList, conf.BlockedUserIDs())
				require.Equal(t, c.expectedList, conf.BlockedIPsSHA256Hex())
			})
		}
	})
}
