package ports_test

import (
	"net/http"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/ports"
)

func TestGetClient(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name            string
		typeHeader      string
		versionHeader   string
		setType         bool
		setVersion      bool
		expectedType    string
		expectedVersion string
	}{
		// Valid prism version (allowlisted) -> passthrough.
		{
			name:            "prism-allowlisted",
			typeHeader:      "prism",
			versionHeader:   "v1.12.0",
			setType:         true,
			setVersion:      true,
			expectedType:    "prism",
			expectedVersion: "v1.12.0",
		},
		// Valid type, bad version -> unknown/unknown.
		{
			name:            "prism-bad-version",
			typeHeader:      "prism",
			versionHeader:   "v9.9.9",
			setType:         true,
			setVersion:      true,
			expectedType:    "unknown",
			expectedVersion: "unknown",
		},
		// prism with no version -> unknown/unknown (only one header present).
		{
			name:            "prism-no-version",
			typeHeader:      "prism",
			versionHeader:   "",
			setType:         true,
			setVersion:      true,
			expectedType:    "unknown",
			expectedVersion: "unknown",
		},
		// rainbow only ever reports evergreen -> passthrough.
		{
			name:            "rainbow-evergreen",
			typeHeader:      "rainbow",
			versionHeader:   "evergreen",
			setType:         true,
			setVersion:      true,
			expectedType:    "rainbow",
			expectedVersion: "evergreen",
		},
		// rainbow with a prism version -> unknown/unknown.
		{
			name:            "rainbow-prism-version",
			typeHeader:      "rainbow",
			versionHeader:   "v1.12.0",
			setType:         true,
			setVersion:      true,
			expectedType:    "unknown",
			expectedVersion: "unknown",
		},
		// rainbow with no version -> unknown/unknown.
		{
			name:            "rainbow-no-version",
			typeHeader:      "rainbow",
			versionHeader:   "",
			setType:         true,
			setVersion:      true,
			expectedType:    "unknown",
			expectedVersion: "unknown",
		},
		// Both absent -> missing/missing.
		{
			name:            "both-absent",
			expectedType:    "missing",
			expectedVersion: "missing",
		},
		// Version present, type absent -> unknown/unknown.
		{
			name:            "version-only",
			versionHeader:   "v1.12.0",
			setVersion:      true,
			expectedType:    "unknown",
			expectedVersion: "unknown",
		},
		// Type present, version absent -> unknown/unknown.
		{
			name:            "type-only",
			typeHeader:      "prism",
			setType:         true,
			expectedType:    "unknown",
			expectedVersion: "unknown",
		},
		// Garbage type -> unknown/unknown.
		{
			name:            "garbage-type",
			typeHeader:      "definitely-not-a-real-client",
			versionHeader:   "v1.12.0",
			setType:         true,
			setVersion:      true,
			expectedType:    "unknown",
			expectedVersion: "unknown",
		},
		// evergreen is rainbow-only; prism+evergreen -> unknown/unknown.
		{
			name:            "prism-evergreen",
			typeHeader:      "prism",
			versionHeader:   "evergreen",
			setType:         true,
			setVersion:      true,
			expectedType:    "unknown",
			expectedVersion: "unknown",
		},
		// Empty-string headers behave like absent (both) -> missing/missing.
		{
			name:            "empty-strings",
			setType:         true,
			setVersion:      true,
			expectedType:    "missing",
			expectedVersion: "missing",
		},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			t.Parallel()

			header := http.Header{}
			if c.setType {
				header.Set("X-Client-Type", c.typeHeader)
			}
			if c.setVersion {
				header.Set("X-Client-Version", c.versionHeader)
			}
			request := &http.Request{Header: header}

			client := ports.GetClient(request)
			require.Equal(t, c.expectedType, client.Type)
			require.Equal(t, c.expectedVersion, client.Version)
		})
	}
}

func TestGetClientTruncatesRawValues(t *testing.T) {
	t.Parallel()

	longType := strings.Repeat("a", 1000)
	longVersion := strings.Repeat("b", 1000)

	request := &http.Request{
		Header: http.Header{
			"X-Client-Type":    []string{longType},
			"X-Client-Version": []string{longVersion},
		},
	}

	client := ports.GetClient(request)

	require.Len(t, client.RawType, 50)
	require.Len(t, client.RawVersion, 50)
	require.Equal(t, strings.Repeat("a", 50), client.RawType)
	require.Equal(t, strings.Repeat("b", 50), client.RawVersion)
	// Oversized, unrecognized values still normalize to unknown.
	require.Equal(t, "unknown", client.Type)
	require.Equal(t, "unknown", client.Version)
}

func TestClientMetricAttributes(t *testing.T) {
	t.Parallel()

	request := &http.Request{
		Header: http.Header{
			"X-Client-Type":    []string{"prism"},
			"X-Client-Version": []string{"v1.12.0"},
		},
	}

	attrs := ports.GetClient(request).MetricAttributes()
	require.Len(t, attrs, 2)

	got := map[string]string{}
	for _, a := range attrs {
		got[string(a.Key)] = a.Value.AsString()
	}
	require.Equal(t, "prism", got["client_type"])
	require.Equal(t, "v1.12.0", got["client_version"])
}
