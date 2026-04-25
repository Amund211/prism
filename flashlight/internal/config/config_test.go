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

var allVariablesExceptEnv = []string{"CLOUDSQL_UNIX_SOCKET", "DB_PASSWORD", "DB_USERNAME", "SENTRY_DSN", "HYPIXEL_API_KEY", "BLOCKED_IPS", "BLOCKED_USER_AGENTS", "BLOCKED_USER_IDS", "BLOCKED_IPS_SHA256_HEX"}

func TestGetConfig(t *testing.T) {
	compareConfig := func(t *testing.T, socketPath, username, password, sentryDSN, hypixelAPIKey string, blockedIPs, blockedUserAgents, blockedUserIDs, blockedIPsSHA256Hex []string, env environment, conf config.Config) {
		t.Helper()
		require.Equal(t, socketPath, conf.CloudSQLUnixSocketPath())
		require.Equal(t, username, conf.DBUsername())
		require.Equal(t, password, conf.DBPassword())
		require.Equal(t, sentryDSN, conf.SentryDSN())
		require.Equal(t, hypixelAPIKey, conf.HypixelAPIKey())
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
			compareConfig(t, "", "", "", "", "", []string{}, []string{}, []string{}, []string{}, development, conf)
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
				compareConfig(t, "CLOUDSQL_UNIX_SOCKET", "DB_USERNAME", "DB_PASSWORD", "SENTRY_DSN", "HYPIXEL_API_KEY", []string{"BLOCKED_IPS"}, []string{"BLOCKED_USER_AGENTS"}, []string{"BLOCKED_USER_IDS"}, []string{"BLOCKED_IPS_SHA256_HEX"}, env, conf)
			})
		}

		t.Run("no sensitive data in NonSensitiveString", func(t *testing.T) {
			t.Setenv("FLASHLIGHT_ENVIRONMENT", string(production))
			conf, err := config.ConfigFromEnv()
			require.NoError(t, err)

			for _, sensitive := range []string{"DB_PASSWORD", "HYPIXEL_API_KEY", "SENTRY_DSN"} {
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
						err := os.Unsetenv(variable)
						require.NoError(t, err)
						t.Cleanup(func() {
							t.Setenv(variable, "placeholder_value")
						})

						_, err = config.ConfigFromEnv()
						require.ErrorIs(t, err, config.ErrMissingRequiredValue)
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
				name:         "line with only comment",
				envValue:     "# this is just a comment",
				expectedList: []string{""},
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
				expectedList: []string{"", "", "value1"},
			},
			{
				name: "complex real-world example",
				envValue: `192.168.1.1 # suspicious IP
192.168.1.2# another one
192.168.1.3
  192.168.1.4  # IP with spaces
# 192.168.1.5 commented out IP
192.168.1.6 # comment with # multiple # hashes`,
				expectedList: []string{"192.168.1.1", "192.168.1.2", "192.168.1.3", "192.168.1.4", "", "192.168.1.6"},
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
