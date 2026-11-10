package ports

import (
	"encoding/json"
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
	"go.opentelemetry.io/otel/attribute"
)

func TestParseSolverReport(t *testing.T) {
	t.Parallel()

	const age = 10 * time.Second

	t.Run("valid report", func(t *testing.T) {
		t.Parallel()
		raw := json.RawMessage(`{"name":"sha-ni","version":"3","hashes":1048576,"elapsedSeconds":0.041,"cpuSeconds":0.04}`)
		report, ok := parseSolverReport(raw, age)
		require.True(t, ok)
		require.Equal(t, solverReport{
			Name:           "sha-ni",
			Version:        "3",
			Hashes:         1048576,
			ElapsedSeconds: 0.041,
			CPUSeconds:     ptr(0.04),
		}, report)
	})

	t.Run("cpuSeconds is optional", func(t *testing.T) {
		t.Parallel()
		report, ok := parseSolverReport(json.RawMessage(`{"name":"worker","version":"1","hashes":10,"elapsedSeconds":0.005}`), age)
		require.True(t, ok)
		require.Nil(t, report.CPUSeconds)
	})

	t.Run("elapsed equal to the challenge age is possible", func(t *testing.T) {
		t.Parallel()
		_, ok := parseSolverReport(json.RawMessage(`{"name":"python","hashes":1,"elapsedSeconds":10}`), age)
		require.True(t, ok)
	})

	for name, raw := range map[string]string{
		"absent":                     "",
		"null":                       "null",
		"empty object":               `{}`,
		"no name":                    `{"version":"1","hashes":1,"elapsedSeconds":1}`,
		"no hashes":                  `{"name":"sha-ni","elapsedSeconds":1}`,
		"not an object":              `"sha-ni"`,
		"wrong field type":           `{"name":"sha-ni","hashes":"many","elapsedSeconds":1}`,
		"negative hashes":            `{"name":"sha-ni","hashes":-1,"elapsedSeconds":1}`,
		"negative elapsedSeconds":    `{"name":"sha-ni","hashes":1,"elapsedSeconds":-1}`,
		"negative cpuSeconds":        `{"name":"sha-ni","hashes":1,"elapsedSeconds":1,"cpuSeconds":-1}`,
		"fractional hashes":          `{"name":"sha-ni","hashes":1.5,"elapsedSeconds":1}`,
		"elapsed past challenge age": `{"name":"sha-ni","hashes":1,"elapsedSeconds":10.001}`,
		"huge elapsed":               `{"name":"sha-ni","hashes":1,"elapsedSeconds":1e300}`,
		"long name":                  `{"name":"` + strings.Repeat("x", 33) + `","hashes":1,"elapsedSeconds":1}`,
		"long version":               `{"name":"sha-ni","version":"` + strings.Repeat("1", 33) + `","hashes":1,"elapsedSeconds":1}`,
		"multibyte over 32 bytes":    `{"name":"` + strings.Repeat("é", 17) + `","hashes":1,"elapsedSeconds":1}`,
		"raw over the byte cap":      `{"name":"sha-ni","hashes":1,"elapsedSeconds":1,"pad":"` + strings.Repeat("x", solverReportMaxBytes) + `"}`,
	} {
		t.Run("ignores "+name, func(t *testing.T) {
			t.Parallel()
			_, ok := parseSolverReport(json.RawMessage(raw), age)
			require.False(t, ok)
		})
	}
}

func TestSolverReportMetricAttributes(t *testing.T) {
	t.Parallel()

	attrs := func(report solverReport) map[attribute.Key]string {
		out := map[attribute.Key]string{}
		for _, kv := range report.metricAttributes() {
			out[kv.Key] = kv.Value.String()
		}
		return out
	}

	t.Run("known name and version pass through", func(t *testing.T) {
		t.Parallel()
		for _, name := range []string{"python", "portable", "sha-ni", "armv8", "worker", "inline"} {
			for _, version := range []string{"1", "2", "3", "4", "5"} {
				got := attrs(solverReport{Name: name, Version: version})
				require.Equal(t, name, got["solver_name"])
				require.Equal(t, version, got["solver_version"])
			}
		}
	})

	t.Run("unknown name collapses to other", func(t *testing.T) {
		t.Parallel()
		require.Equal(t, "other", attrs(solverReport{Name: "gpu", Version: "1"})["solver_name"])
	})

	t.Run("unknown version collapses to other", func(t *testing.T) {
		t.Parallel()
		for _, version := range []string{"", "0", "6", "10", "v1", "1.0", "01"} {
			require.Equal(t, "other", attrs(solverReport{Name: "sha-ni", Version: version})["solver_version"], version)
		}
	})
}

func TestSolverReportHashRate(t *testing.T) {
	t.Parallel()

	rate, ok := solverReport{Hashes: 1000, ElapsedSeconds: 0.0005}.hashesPerSecond()
	require.True(t, ok)
	require.InDelta(t, 2e6, rate, 1e-6)

	_, ok = solverReport{Hashes: 1000, ElapsedSeconds: 0}.hashesPerSecond()
	require.False(t, ok, "a zero elapsed time has no rate")
}

func ptr[T any](v T) *T { return &v }
