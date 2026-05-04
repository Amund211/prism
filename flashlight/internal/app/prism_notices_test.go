package app_test

import (
	"testing"
	"time"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/app"
	"github.com/Amund211/flashlight/internal/domaintest"
)

func TestBuildGetPrismNotices(t *testing.T) {
	t.Parallel()

	defaultTime := time.Date(2024, time.June, 1, 0, 0, 0, 0, time.UTC)

	cases := []struct {
		name            string
		userID          string
		prismVersion    string
		updateSelection app.UpdateSelection
		now             time.Time
		want            []app.PrismNotice
	}{
		{
			name:            "empty inputs",
			userID:          "",
			prismVersion:    "",
			updateSelection: app.UpdateSelectionNone,
			now:             defaultTime,
			want:            []app.PrismNotice{},
		},
		{
			name:            "v1.10.1-dev outside wrapped window",
			userID:          domaintest.NewUUID(t),
			prismVersion:    "v1.10.1-dev",
			updateSelection: app.UpdateSelectionNone,
			now:             defaultTime,
			want:            []app.PrismNotice{},
		},
		{
			name:            "wrapped notice surfaced at start of December",
			userID:          domaintest.NewUUID(t),
			prismVersion:    "v1.11.0",
			updateSelection: app.UpdateSelectionNone,
			now:             time.Date(2025, time.December, 1, 0, 0, 0, 0, time.UTC),
			want: []app.PrismNotice{
				{
					Message:         "Click here to view your Prism Wrapped 2025",
					URL:             "https://prismoverlay.com/wrapped",
					Severity:        app.SeverityInfo,
					DurationSeconds: new(60.0),
				},
			},
		},
		{
			name:            "wrapped notice surfaced on Christmas Eve",
			userID:          domaintest.NewUUID(t),
			prismVersion:    "v1.11.0",
			updateSelection: app.UpdateSelectionNone,
			now:             time.Date(2025, time.December, 24, 0, 0, 0, 0, time.UTC),
			want: []app.PrismNotice{
				{
					Message:         "Click here to view your Prism Wrapped 2025",
					URL:             "https://prismoverlay.com/wrapped",
					Severity:        app.SeverityInfo,
					DurationSeconds: new(60.0),
				},
			},
		},
		{
			name:            "wrapped notice surfaced on last day of January reports prior year",
			userID:          domaintest.NewUUID(t),
			prismVersion:    "v1.11.0",
			updateSelection: app.UpdateSelectionNone,
			now:             time.Date(2026, time.January, 31, 23, 59, 59, 0, time.UTC),
			want: []app.PrismNotice{
				{
					Message:         "Click here to view your Prism Wrapped 2025",
					URL:             "https://prismoverlay.com/wrapped",
					Severity:        app.SeverityInfo,
					DurationSeconds: new(60.0),
				},
			},
		},
		{
			name:            "wrapped window closed in February",
			userID:          domaintest.NewUUID(t),
			prismVersion:    "v1.11.0",
			updateSelection: app.UpdateSelectionNone,
			now:             time.Date(2026, time.February, 1, 0, 0, 0, 0, time.UTC),
			want:            []app.PrismNotice{},
		},
		{
			name:            "known unicode replacement character user gets warning notice",
			userID:          "b1b6ead3b357467298c0a186a891940f",
			prismVersion:    "v1.11.0",
			updateSelection: app.UpdateSelectionNone,
			now:             defaultTime,
			want: []app.PrismNotice{
				{
					Message:         "We've detected a potential issue with your Prism client.\nPlease click here to create a ticket in the discord server",
					URL:             "https://discord.gg/NGpRrdh6Fx",
					Severity:        app.SeverityWarning,
					DurationSeconds: new(120.0),
				},
			},
		},

		// Version-update-focused cases.
		{
			// v1.11.0 sends no preference, so the handler defaults to All.
			name:            "v1.11.0 still has local checker",
			userID:          domaintest.NewUUID(t),
			prismVersion:    "v1.11.0",
			updateSelection: app.UpdateSelectionAll,
			now:             defaultTime,
			want:            []app.PrismNotice{},
		},
		{
			name:            "selection=none with unparseable version",
			userID:          domaintest.NewUUID(t),
			prismVersion:    "not-a-version",
			updateSelection: app.UpdateSelectionNone,
			now:             defaultTime,
			want:            []app.PrismNotice{},
		},
		{
			name:            "selection=minor with unparseable version",
			userID:          domaintest.NewUUID(t),
			prismVersion:    "not-a-version",
			updateSelection: app.UpdateSelectionMinor,
			now:             defaultTime,
			want:            []app.PrismNotice{},
		},
		{
			name:            "selection=all with unparseable version",
			userID:          domaintest.NewUUID(t),
			prismVersion:    "not-a-version",
			updateSelection: app.UpdateSelectionAll,
			now:             defaultTime,
			want:            []app.PrismNotice{},
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			nowFunc := func() time.Time { return tc.now }
			getPrismNotices := app.BuildGetPrismNotices(nowFunc)

			got := getPrismNotices(t.Context(), tc.userID, tc.prismVersion, tc.updateSelection)

			require.Equal(t, tc.want, got)
		})
	}
}
