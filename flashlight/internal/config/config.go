package config

import (
	"errors"
	"fmt"
	"os"
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
	env                    environment
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

func (c *Config) IsProduction() bool {
	return c.env == production
}

func (c *Config) IsStaging() bool {
	return c.env == staging
}

func (c *Config) IsDevelopment() bool {
	return c.env == development
}

// Return a string representation suitable for logging etc
func (c *Config) NonSensitiveString() string {
	return fmt.Sprintf("Config{env: %s, ...}", string(c.env))
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

	cloudSQLUnixSocketPath := os.Getenv("CLOUDSQL_UNIX_SOCKET")
	dbPassword := os.Getenv("DB_PASSWORD")
	dbUsername := os.Getenv("DB_USERNAME")
	sentryDSN := os.Getenv("SENTRY_DSN")
	hypixelAPIKey := os.Getenv("HYPIXEL_API_KEY")

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
	}

	return Config{
		cloudSQLUnixSocketPath: cloudSQLUnixSocketPath,
		dBPassword:             dbPassword,
		dBUsername:             dbUsername,
		sentryDSN:              sentryDSN,
		hypixelAPIKey:          hypixelAPIKey,
		env:                    env,
	}, nil
}
