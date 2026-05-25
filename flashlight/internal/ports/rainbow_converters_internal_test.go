package ports

import (
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/domain"
)

func TestGamemodeToRainbowGamemode(t *testing.T) {
	t.Parallel()

	tests := []struct {
		gamemode domain.Gamemode
		want     string
		wantErr  bool
	}{
		{gamemode: domain.GamemodeSolo, want: "solo"},
		{gamemode: domain.GamemodeDoubles, want: "doubles"},
		{gamemode: domain.GamemodeThrees, want: "threes"},
		{gamemode: domain.GamemodeFours, want: "fours"},
		{gamemode: domain.GamemodeOverall, want: "overall"},
		{gamemode: domain.Gamemode("???"), wantErr: true},
	}

	for _, tt := range tests {
		t.Run(string(tt.gamemode), func(t *testing.T) {
			t.Parallel()

			got, err := gamemodeToRainbowGamemode(tt.gamemode)
			if tt.wantErr {
				require.Error(t, err)
				require.Empty(t, got)
				return
			}
			require.NoError(t, err)
			require.Equal(t, tt.want, got)
		})
	}
}
