package ports

import (
	"fmt"
	"net/http"

	"go.opentelemetry.io/otel/attribute"
)

const (
	clientTypePrism   = "prism"
	clientTypeRainbow = "rainbow"
	clientTypeUnknown = "unknown"
	clientTypeMissing = "missing"

	clientVersionEvergreen = "evergreen"
	clientVersionUnknown   = "unknown"
	clientVersionMissing   = "missing"
)

// knownPrismVersions is the allowlist of accepted X-Client-Version values for
// the prism client. Keep it SHORT — prune old versions as clients age out — to
// bound metric cardinality. No prism client sends these headers yet; v1.12.0
// (the upcoming release) is seeded so the pipeline is ready when it ships.
var knownPrismVersions = map[string]struct{}{
	"v1.11.1-dev": {},
	"v1.12.0":     {},
	"v1.12.1-dev": {},
}

// Client is the normalized identity of the calling client, derived from the
// X-Client-Type and X-Client-Version request headers. Raw values are retained
// (truncated) for logging; Type and Version are the bounded, allowlisted values
// safe to use as metric labels.
type Client struct {
	RawType    string
	RawVersion string
	Type       string
	Version    string
}

// GetClient reads and normalizes the client identity from the request headers.
func GetClient(r *http.Request) Client {
	// Truncate raw values before retaining them — they are client-controlled
	// and must not bloat logs (mirrors GetUserID).
	rawType := fmt.Sprintf("%.50s", r.Header.Get("X-Client-Type"))
	rawVersion := fmt.Sprintf("%.50s", r.Header.Get("X-Client-Version"))

	clientType, clientVersion := normalizeClient(rawType, rawVersion)

	return Client{
		RawType:    rawType,
		RawVersion: rawVersion,
		Type:       clientType,
		Version:    clientVersion,
	}
}

// normalizeClient validates the (type, version) pair jointly and returns a
// bounded normalized pair. Because validation is joint, the normalized pair is
// never a cross-product — it is one of the allowlisted prism pairs,
// (rainbow, evergreen), (missing, missing), or (unknown, unknown) — which keeps
// the metric label cardinality bounded regardless of client input.
func normalizeClient(rawType, rawVersion string) (clientType string, clientVersion string) {
	// Both headers absent.
	if rawType == "" && rawVersion == "" {
		return clientTypeMissing, clientVersionMissing
	}

	// prism with an allowlisted version.
	if rawType == clientTypePrism {
		if _, ok := knownPrismVersions[rawVersion]; ok {
			return clientTypePrism, rawVersion
		}
	}

	// rainbow only ever reports the evergreen version.
	if rawType == clientTypeRainbow && rawVersion == clientVersionEvergreen {
		return clientTypeRainbow, clientVersionEvergreen
	}

	// Everything else — unknown type, valid type with a bad version, or exactly
	// one header present — collapses to unknown.
	return clientTypeUnknown, clientVersionUnknown
}

// MetricAttributes returns the bounded client labels for metric instruments.
// Kept here so the call sites stay consistent.
func (c Client) MetricAttributes() []attribute.KeyValue {
	return []attribute.KeyValue{
		attribute.String("client_type", c.Type),
		attribute.String("client_version", c.Version),
	}
}
