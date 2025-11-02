package logging

import (
	"context"
	"fmt"
	"log/slog"

	"go.opentelemetry.io/otel/trace"
)

// Create a slog.Handler that adds Google Cloud Trace fields to log records
//
// NOTE: Requires the use of the *Context slog methods to get the tracing info
func NewGoogleCloudTracingLogHandler(baseHandler slog.Handler, project string) *googleCloudTracingLogHandler {
	return &googleCloudTracingLogHandler{base: baseHandler, project: project}
}

type googleCloudTracingLogHandler struct {
	base    slog.Handler
	project string
}

func (h *googleCloudTracingLogHandler) Enabled(ctx context.Context, level slog.Level) bool {
	return h.base.Enabled(ctx, level)
}

func (h *googleCloudTracingLogHandler) Handle(ctx context.Context, r slog.Record) error {
	if sc := trace.SpanContextFromContext(ctx); sc.IsValid() {
		// Associate the logs in google cloud with the active trace/span.
		// https://docs.cloud.google.com/logging/docs/agent/logging/configuration#special-fields
		qualifiedTraceID := fmt.Sprintf("projects/%s/traces/%s", h.project, sc.TraceID().String())
		r.AddAttrs(
			slog.String("logging.googleapis.com/trace", qualifiedTraceID),
			slog.String("logging.googleapis.com/spanId", sc.SpanID().String()),
			slog.Bool("logging.googleapis.com/trace_sampled", sc.TraceFlags().IsSampled()),
		)
	}
	return h.base.Handle(ctx, r)
}

func (h *googleCloudTracingLogHandler) WithAttrs(attrs []slog.Attr) slog.Handler {
	return NewGoogleCloudTracingLogHandler(h.base.WithAttrs(attrs), h.project)
}

func (h *googleCloudTracingLogHandler) WithGroup(name string) slog.Handler {
	return NewGoogleCloudTracingLogHandler(h.base.WithGroup(name), h.project)
}

// Type assertion
var _ slog.Handler = (*googleCloudTracingLogHandler)(nil)
