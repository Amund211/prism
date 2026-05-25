package domain

// Gamemode names a Bedwars team-size mode. GamemodeOverall is not a
// real in-game mode — it's the aggregate scope used by stat queries
// and milestone tracking — but it lives on the same type for parity
// with the per-mode values.
type Gamemode string

const (
	GamemodeSolo    Gamemode = "solo"
	GamemodeDoubles Gamemode = "doubles"
	GamemodeThrees  Gamemode = "threes"
	GamemodeFours   Gamemode = "fours"
	GamemodeOverall Gamemode = "overall"
)
