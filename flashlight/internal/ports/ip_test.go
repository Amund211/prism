package ports_test

import (
	"net/http"
	"testing"

	"github.com/Amund211/flashlight/internal/ports"
	"github.com/stretchr/testify/require"
)

func TestGetIP(t *testing.T) {
	t.Parallel()

	cases := []struct {
		remoteAddr    string
		xForwardedFor string
		ip            string
	}{
		{
			// Connecting through GCP load balancer
			remoteAddr:    "169.254.169.126:58418",
			xForwardedFor: "12.12.123.123,34.111.7.239",
			ip:            "12.12.123.123",
		},
		{
			// Connecting through GCP load balancer
			// Attempt to inject invalid IP via X-Forwarded-For
			// https://docs.cloud.google.com/load-balancing/docs/https#x-forwarded-for_header
			// > If the incoming request already includes an X-Forwarded-For header, the load balancer appends its values to the existing header:
			// > X-Forwarded-For: <existing-value>,<client-ip>,<load-balancer-ip>
			// Client sends X-Forwarded-For: 127.0.0.1
			// We receive:
			remoteAddr:    "169.254.169.126:44548",
			xForwardedFor: "127.0.0.1,12.123.123.1,34.111.7.239",
			ip:            "12.123.123.1",
		},
		{
			// Connecting through GCP load balancer
			// Attempt to inject invalid IP via X-Forwarded-For
			// Client sends X-Forwarded-For: 127.0.0.1,123.123.123.123
			// We receive:
			remoteAddr:    "169.254.169.126:54138",
			xForwardedFor: "127.0.0.1,123.123.123.123,12.123.123.1,34.111.7.239",
			ip:            "12.123.123.1",
		},
		{
			// Connecting directly to the cloud run service (run.app)
			remoteAddr:    "169.254.169.126:10910",
			xForwardedFor: "1111:111:1111:1111:1111:1111:1111:1111",
			ip:            "1111:111:1111:1111:1111:1111:1111:1111",
		},
		{
			// Connecting directly to the cloud run service (run.app)
			// Attempt to inject invalid IP via X-Forwarded-For
			// Client sends X-Forwarded-For: 127.0.0.1
			// We receive:
			remoteAddr:    "169.254.169.126:15050",
			xForwardedFor: "127.0.0.1,1111:111:1111:1111:1111:1111:1111:1111",
			ip:            "1111:111:1111:1111:1111:1111:1111:1111",
		},
		{
			// Connecting directly to the cloud run service (run.app)
			// Attempt to inject invalid IP via X-Forwarded-For
			// Client sends X-Forwarded-For: 127.0.0.1,123.123.123.123
			// We receive:
			remoteAddr:    "169.254.169.126:3122",
			xForwardedFor: "127.0.0.1,123.123.123.123,1111:111:1111:1111:1111:1111:1111:1111",
			ip:            "1111:111:1111:1111:1111:1111:1111:1111",
		},
		{
			// NOTE: Constructed case - not seen in production
			// No X-Forwarded-For header
			remoteAddr: "123.123.123.123",
			ip:         "<missing>",
		},
		{
			// NOTE: Constructed case - not seen in production
			// Invalid client ip in xff
			xForwardedFor: "invalid-ip",
			ip:            "<invalid>",
		},
		{
			// NOTE: Constructed case - not seen in production
			// Invalid client ip in xff
			xForwardedFor: "127.0.0.1,invalid-ip",
			ip:            "<invalid>",
		},
		{
			// NOTE: Constructed case - not seen in production
			// Invalid client ip in xff
			xForwardedFor: "invalid-ip,34.111.7.239",
			ip:            "<invalid>",
		},
		{
			// NOTE: Constructed case - not seen in production
			// Invalid client ip in xff
			xForwardedFor: "127.0.0.1,invalid-ip,34.111.7.239",
			ip:            "<invalid>",
		},
		{
			// NOTE: Constructed case - not seen in production
			// No client ip after removing load balancer ip
			xForwardedFor: "34.111.7.239",
			ip:            "<missing>",
		},
	}
	for _, c := range cases {
		t.Run(c.xForwardedFor, func(t *testing.T) {
			t.Parallel()

			req, err := http.NewRequest("GET", "/", nil)
			require.NoError(t, err)
			req.RemoteAddr = c.remoteAddr
			if c.xForwardedFor != "" {
				req.Header.Add("X-Forwarded-For", c.xForwardedFor)
			}
			require.Equal(t, c.ip, ports.GetIP(req))
		})
	}
}
