package reporting

import (
	"fmt"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestSanitizeError(t *testing.T) {
	t.Parallel()

	t.Run("connection reset by peer", func(t *testing.T) {
		t.Parallel()

		err := `Server error: Get "https://api.hypixel.net/player?uuid=deadbeef8315465d9d44cfc238c64f71": read tcp [dead:beef:feb1:d745::c001]:64079->[dead:beef::6811:112a]:443: read: connection reset by peer`
		want := `Server error: Get "https://api.hypixel.net/player?uuid=<uuid>": read tcp <host>-><host>: read: connection reset by peer`
		require.Equal(t, want, sanitizeError(err))
	})
	t.Run("context deadline", func(t *testing.T) {
		t.Parallel()

		err := `Server error: Get "https://api.hypixel.net/player?uuid=deadbeef810845ca8424cf7ba5929a3e": context deadline exceeded (Client.Timeout exceeded while awaiting headers)`
		want := `Server error: Get "https://api.hypixel.net/player?uuid=<uuid>": context deadline exceeded (Client.Timeout exceeded while awaiting headers)`
		require.Equal(t, want, sanitizeError(err))
	})
	t.Run("misc ipv6", func(t *testing.T) {
		t.Parallel()

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
				t.Parallel()

				require.Equal(t, "<host>", sanitizeError(fmt.Sprintf("[%s]:1234", ip)))
			})
		}
	})
	t.Run("username requests", func(t *testing.T) {
		t.Parallel()

		cases := []struct {
			error string
			want  string
		}{
			{
				// Real error
				error: `failed to send request: Get "https://api.mojang.com/users/profiles/minecraft/ZteelyX": context deadline exceeded (Client.Timeout exceeded while awaiting headers)`,
				want:  `failed to send request: Get "https://api.mojang.com/users/profiles/minecraft/<username>": context deadline exceeded (Client.Timeout exceeded while awaiting headers)`,
			},
			{
				// Real error
				error: `failed to send request: Get "https://api.mojang.com/users/profiles/minecraft/MrMocchi": context deadline exceeded (Client.Timeout exceeded while awaiting headers)`,
				want:  `failed to send request: Get "https://api.mojang.com/users/profiles/minecraft/<username>": context deadline exceeded (Client.Timeout exceeded while awaiting headers)`,
			},
			{
				// Constructed - no match
				error: `failed to send request: Get "https://api.mojang.com/users/profiles/minecraft/player with spaces": failed`,
				want:  `failed to send request: Get "https://api.mojang.com/users/profiles/minecraft/player with spaces": failed`,
			},
			{
				// Constructed - don't match eagerly
				error: `failed to send request: Get "https://api.mojang.com/users/profiles/minecraft/someplayer": failed due to "some sort of error"`,
				want:  `failed to send request: Get "https://api.mojang.com/users/profiles/minecraft/<username>": failed due to "some sort of error"`,
			},
			{
				// Constructed - don't match eagerly
				error: `failed to send request: Get "https://api.mojang.com/users/profiles/minecraft/someplayer":"someextraerrorhere"`,
				want:  `failed to send request: Get "https://api.mojang.com/users/profiles/minecraft/<username>":"someextraerrorhere"`,
			},
		}
		for _, tc := range cases {
			t.Run(tc.error, func(t *testing.T) {
				t.Parallel()

				require.Equal(t, tc.want, sanitizeError(tc.error))
			})
		}
	})
}
