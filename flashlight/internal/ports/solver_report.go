package ports

import (
	"bytes"
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"time"

	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/metric"

	"github.com/Amund211/flashlight/internal/logging"
)

// solverReport is the client's account of how it solved the proof of work.
// It is client-supplied: use it for statistics only, never for a decision.
type solverReport struct {
	Name           string   `json:"name"`
	Version        string   `json:"version"`
	Hashes         int64    `json:"hashes"`
	ElapsedSeconds float64  `json:"elapsedSeconds"`
	CPUSeconds     *float64 `json:"cpuSeconds"`
}

const solverReportStringMaxLength = 32

// solverReportMaxBytes bounds the raw solver field: two strings at the cap,
// every character escaped to six bytes, three numbers and the keys.
const solverReportMaxBytes = 1024

var knownSolverNames = map[string]struct{}{
	// prism
	"python":   {},
	"portable": {},
	"sha-ni":   {},
	"armv8":    {},
	// rainbow
	"worker": {},
	"inline": {},
}

// knownSolverVersions bounds the solver_version label. Add a version here
// before a client ships it.
var knownSolverVersions = map[string]struct{}{
	"1": {},
	"2": {},
	"3": {},
	"4": {},
	"5": {},
}

// parseSolverReport returns the report and true, or false for anything absent,
// malformed or out of bounds. A report that claims a solve longer than the
// challenge has existed is impossible, so it is dropped too.
func parseSolverReport(raw json.RawMessage, challengeAge time.Duration) (solverReport, bool) {
	if len(raw) == 0 || len(raw) > solverReportMaxBytes || bytes.Equal(raw, []byte("null")) {
		return solverReport{}, false
	}

	var report solverReport
	if err := json.Unmarshal(raw, &report); err != nil {
		return solverReport{}, false
	}

	if report.Name == "" || len(report.Name) > solverReportStringMaxLength || len(report.Version) > solverReportStringMaxLength {
		return solverReport{}, false
	}
	if report.Hashes <= 0 || report.ElapsedSeconds < 0 || (report.CPUSeconds != nil && *report.CPUSeconds < 0) {
		return solverReport{}, false
	}
	if report.ElapsedSeconds > challengeAge.Seconds() {
		return solverReport{}, false
	}

	return report, true
}

func (s solverReport) metricAttributes() []attribute.KeyValue {
	name := "other"
	if _, ok := knownSolverNames[s.Name]; ok {
		name = s.Name
	}
	version := "other"
	if _, ok := knownSolverVersions[s.Version]; ok {
		version = s.Version
	}
	return []attribute.KeyValue{
		attribute.String("solver_name", name),
		attribute.String("solver_version", version),
	}
}

func (s solverReport) hashesPerSecond() (float64, bool) {
	if s.ElapsedSeconds <= 0 {
		return 0, false
	}
	return float64(s.Hashes) / s.ElapsedSeconds, true
}

// recordSolverReport logs and samples a report from a login whose proof
// verified. Anything it cannot parse is dropped silently.
func recordSolverReport(ctx context.Context, r *http.Request, raw json.RawMessage, challengeAge time.Duration, difficulty int) {
	report, ok := parseSolverReport(raw, challengeAge)
	if !ok {
		return
	}

	client := GetClient(r)

	logArgs := []any{
		slog.String("clientType", client.Type),
		slog.String("clientVersion", client.Version),
		slog.String("name", report.Name),
		slog.String("version", report.Version),
		slog.Int64("hashes", report.Hashes),
		slog.Float64("elapsedSeconds", report.ElapsedSeconds),
		slog.Int("difficulty", difficulty),
	}
	if report.CPUSeconds != nil {
		logArgs = append(logArgs, slog.Float64("cpuSeconds", *report.CPUSeconds))
	}
	logging.FromContext(ctx).InfoContext(ctx, "Proof of work solver report", slog.Group("solver", logArgs...))

	attributes := metric.WithAttributes(append(
		append(client.MetricAttributes(), report.metricAttributes()...),
		attribute.Int("difficulty", difficulty),
	)...)

	metrics.powSolveDuration.Record(ctx, report.ElapsedSeconds, attributes)
	if rate, ok := report.hashesPerSecond(); ok {
		metrics.powSolveHashRate.Record(ctx, rate, attributes)
	}
}
