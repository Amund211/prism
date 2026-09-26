package microsoftauth

import "log/slog"

const redacted = "[REDACTED]"

// secret is a token the chain holds for one request. Every way to print,
// log or encode it yields [REDACTED]; reveal is the one way out, and only
// the request that sends it calls it.
type secret string

func (s secret) reveal() string {
	return string(s)
}

func (secret) String() string {
	return redacted
}

func (secret) GoString() string {
	return redacted
}

func (secret) LogValue() slog.Value {
	return slog.StringValue(redacted)
}

func (secret) MarshalText() ([]byte, error) {
	return []byte(redacted), nil
}
