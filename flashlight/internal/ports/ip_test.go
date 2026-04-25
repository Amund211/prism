package ports_test

import (
	"encoding/hex"
	"net/http"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/ports"
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

			req, err := http.NewRequestWithContext(t.Context(), "GET", "/", http.NoBody)
			require.NoError(t, err)
			req.RemoteAddr = c.remoteAddr
			if c.xForwardedFor != "" {
				req.Header.Add("X-Forwarded-For", c.xForwardedFor)
			}
			require.Equal(t, c.ip, ports.GetIP(req).String())
		})
	}
}

func TestGetIP_Hash(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name          string
		remoteAddr    string
		xForwardedFor string
		expectedIP    string
		expectedHash  string
	}{
		{
			name:          "valid IP through GCP load balancer",
			remoteAddr:    "169.254.169.126:58418",
			xForwardedFor: "12.12.123.123,34.111.7.239",
			expectedIP:    "12.12.123.123",
			expectedHash:  "d41e06ebd38060ce31e76914ca59460fe105a24afcb8d95e23f55ae96a1b975b",
		},
		{
			name:          "valid IPv6 address",
			remoteAddr:    "169.254.169.126:10910",
			xForwardedFor: "1111:111:1111:1111:1111:1111:1111:1111",
			expectedIP:    "1111:111:1111:1111:1111:1111:1111:1111",
			expectedHash:  "a985589851594403e0087a0b6d1eca667550fca64e7c41a58bee08b3f973d161",
		},
		{
			name:         "missing X-Forwarded-For header",
			remoteAddr:   "123.123.123.123",
			expectedIP:   "<missing>",
			expectedHash: "769b8995b8bf4407c89e906d67601a46266d34922a63ab1754440eecb0657aab",
		},
		{
			name:          "invalid client IP",
			xForwardedFor: "invalid-ip",
			expectedIP:    "<invalid>",
			expectedHash:  "4253d86ac6a32c8a07df39bc28a231eca200747e18f10b18a7dcae29cd5c3e54",
		},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			t.Parallel()

			req, err := http.NewRequestWithContext(t.Context(), "GET", "/", http.NoBody)
			require.NoError(t, err)
			req.RemoteAddr = c.remoteAddr
			if c.xForwardedFor != "" {
				req.Header.Add("X-Forwarded-For", c.xForwardedFor)
			}

			// Sanity check that expectedHash matches ports.IP(expectedIP).Hash()
			require.Equal(t, c.expectedHash, ports.IP(c.expectedIP).Hash())

			hash := ports.GetIP(req).Hash()

			// Verify it's a valid hex string
			require.Len(t, hash, 64, "SHA256 hash should be 64 hex characters")
			_, err = hex.DecodeString(hash)
			require.NoError(t, err, "Hash should be valid hex")

			// Verify hash is consistent with the IP
			ip := ports.GetIP(req)
			require.Equal(t, c.expectedIP, ip.String())
			require.Equal(t, c.expectedHash, hash)
		})
	}
}
