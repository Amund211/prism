package config_test

import (
	"testing"

	"github.com/Amund211/flashlight/internal/config"
	"github.com/stretchr/testify/require"
)

type environment string

const (
	production  environment = "production"
	staging     environment = "staging"
	development environment = "development"
)

var allVariablesExceptEnv = []string{"CLOUDSQL_UNIX_SOCKET", "DB_PASSWORD", "DB_USERNAME", "SENTRY_DSN", "HYPIXEL_API_KEY"}

func TestGetConfig(t *testing.T) {
	compareConfig := func(socketPath, username, password, sentryDSN, hypixelAPIKey string, env environment, conf config.Config) {
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
			compareConfig("", "", "", "", "", development, conf)
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
				compareConfig("CLOUDSQL_UNIX_SOCKET", "DB_USERNAME", "DB_PASSWORD", "SENTRY_DSN", "HYPIXEL_API_KEY", env, conf)
			})
		}

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
						t.Setenv(variable, "")

						_, err := config.ConfigFromEnv()
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
}
