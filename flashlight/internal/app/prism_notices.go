package app

import (
	"context"
	"fmt"
	"slices"
	"time"

	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/version"
)

type Severity string

const (
	SeverityInfo     Severity = "info"
	SeverityUpdate   Severity = "update"
	SeverityWarning  Severity = "warning"
	SeverityCritical Severity = "critical"
)

type UpdateSelection int

const (
	UpdateSelectionNone UpdateSelection = iota
	UpdateSelectionMinor
	UpdateSelectionAll
)

type PrismNotice struct {
	Message         string
	URL             string
	Severity        Severity
	DurationSeconds *float64
}

type GetPrismNotices = func(
	ctx context.Context,
	userID string,
	prismVersion string,
	updateSelection UpdateSelection,
) []PrismNotice

// latestPrism is the most recent released prism version. Bump this when
// cutting a new prism release; clients running an older version will be told
// (via the prism-notices endpoint) that an update is available.
var latestPrism = version.MustParse("v1.11.0")

// firstPrismVersionWithoutLocalChecker is the first prism release that does
// not include the in-process GitHub update checker — those clients rely on
// flashlight to surface update notices. Older clients still poll GitHub
// themselves, so flashlight must not duplicate the notice for them.
var firstPrismVersionWithoutLocalChecker = version.MustParse("v1.12.0")

const latestPrismReleaseURL = "https://github.com/Amund211/prism/releases/latest/"

var unicodeReplacementCharacterUsers = []string{
	"b1b6ead3b357467298c0a186a891940f",
	"e104fb8b4b8a4a40ba70334e8239c0e1",
	"b3c71ddfb808414d80e932110dae5716",
	"9c90ae7b927347a787ddb9c9e85cca16",
	"a3ec8094a2bb427f81c11faadb33c2ba",
	"ea2aa5221a614dc1a502f01e33f4ceaa",
	"47e7859bb33246ef8494fb81a9ac4e01",
	"426d836cdc7740bd9ff887d1d8a358f3",

	"3eedaf7ed5964d8981835b8f0de2c9d4",
	"bb683d98dc634a5783be9a4895ab75af",
	"a55dfa5ddaa7426b87f2a5dbc3ad5254",
}

func BuildGetPrismNotices(nowFunc func() time.Time) GetPrismNotices {
	return func(ctx context.Context, userID string, prismVersion string, updateSelection UpdateSelection) []PrismNotice {
		notices := []PrismNotice{}

		now := nowFunc().UTC()

		notices = append(notices, versionUpdateNotices(ctx, prismVersion, updateSelection)...)

		if slices.Contains(unicodeReplacementCharacterUsers, userID) {
			// These users sometimes include a unicode replacement character at the end of
			// usernames sent to the account endpoint, causing issues.
			// https://prism-overlay.sentry.io/issues/7078120764/?project=4506886744768512
			duration := 120.0
			logging.FromContext(ctx).InfoContext(ctx, "Adding critical notice for user with known unicode replacement character issue", "userID", userID)
			notices = append(notices, PrismNotice{
				Message:         "We've detected a potential issue with your Prism client.\nPlease click here to create a ticket in the discord server",
				URL:             "https://discord.gg/NGpRrdh6Fx",
				Severity:        SeverityWarning,
				DurationSeconds: &duration,
			})
		}

		if now.Month() == time.December || now.Month() == time.January {
			duration := 60.0
			year := now.Year()
			if now.Month() == time.January {
				year = year - 1
			}
			notices = append(notices, PrismNotice{
				Message:         fmt.Sprintf("Click here to view your Prism Wrapped %d", year),
				URL:             "https://prismoverlay.com/wrapped",
				Severity:        SeverityInfo,
				DurationSeconds: &duration,
			})
		}

		return notices
	}
}

func versionUpdateNotices(ctx context.Context, prismVersion string, updateSelection UpdateSelection) []PrismNotice {
	if updateSelection == UpdateSelectionNone {
		return nil
	}
	includePatchUpdates := updateSelection == UpdateSelectionAll

	current, err := version.Parse(prismVersion)
	if err != nil {
		logging.FromContext(ctx).WarnContext(ctx, "Failed to parse prism version", "error", err, "prismVersion", prismVersion)
		return nil
	}

	if !current.IsAtLeast(firstPrismVersionWithoutLocalChecker) {
		// This client still has its own GitHub update checker.
		return nil
	}

	if !current.UpdateAvailable(latestPrism, !includePatchUpdates) {
		return nil
	}

	logging.FromContext(ctx).InfoContext(ctx, "Adding prism update notice", "prismVersion", prismVersion, "latest", latestPrism)
	duration := 60.0
	return []PrismNotice{{
		Message:         "New update available! Click here to download.",
		URL:             latestPrismReleaseURL,
		Severity:        SeverityUpdate,
		DurationSeconds: &duration,
	}}
}
