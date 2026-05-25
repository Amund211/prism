package domain

// GameResult describes what happened in a single Bedwars game — which
// gamemode it was played in, whether the player won, and the stat deltas
// that the player accrued during it.
type GameResult struct {
	Gamemode   Gamemode
	Won        bool
	FinalKills int
	FinalDeath bool
	BedsBroken int
	BedLost    bool
	Kills      int
	Deaths     int
	Experience int64
}
