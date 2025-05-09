package reporting

import (
	"fmt"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestSanitizeError(t *testing.T) {
	t.Run("connection reset by peer", func(t *testing.T) {
		err := `Server error: Get "https://api.hypixel.net/player?uuid=deadbeef8315465d9d44cfc238c64f71": read tcp [dead:beef:feb1:d745::c001]:64079->[dead:beef::6811:112a]:443: read: connection reset by peer`
		want := `Server error: Get "https://api.hypixel.net/player?uuid=<uuid>": read tcp <host>-><host>: read: connection reset by peer`
		require.Equal(t, want, sanitizeError(err))
	})
	t.Run("context deadline", func(t *testing.T) {
		err := `Server error: Get "https://api.hypixel.net/player?uuid=deadbeef810845ca8424cf7ba5929a3e": context deadline exceeded (Client.Timeout exceeded while awaiting headers)`
		want := `Server error: Get "https://api.hypixel.net/player?uuid=<uuid>": context deadline exceeded (Client.Timeout exceeded while awaiting headers)`
		require.Equal(t, want, sanitizeError(err))
	})
	t.Run("misc ipv6", func(t *testing.T) {
		ips := []string{
			`1:2:3:4:5:6:7:8`,
			`1::`,
			`1:2:3:4:5:6:7::`,
			`1::8`,
			`1:2:3:4:5:6::8`,
			`1:2:3:4:5:6::8`,
			`1::7:8`,
			`1:2:3:4:5::7:8`,
			`1:2:3:4:5::8`,
			`1::6:7:8`,
			`1:2:3:4::6:7:8`,
			`1:2:3:4::8`,
			`1::5:6:7:8`,
			`1:2:3::5:6:7:8`,
			`1:2:3::8`,
			`1::4:5:6:7:8`,
			`1:2::4:5:6:7:8`,
			`1:2::8`,
			`1::3:4:5:6:7:8`,
			`1::3:4:5:6:7:8`,
			`1::8`,
			`::2:3:4:5:6:7:8`,
			`::8`,
			`::`,
		}
		for _, ip := range ips {
			t.Run(ip, func(t *testing.T) {
				require.Equal(t, "<host>", sanitizeError(fmt.Sprintf("[%s]:1234", ip)))
			})
		}
	})
}
