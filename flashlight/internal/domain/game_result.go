package domain

// GameOutcome names how a single Bedwars game ended for the player.
// Draws are rare but do happen, so the outcome is a three-state enum
// rather than a won/lost boolean.
type GameOutcome string

const (
	GameOutcomeWin  GameOutcome = "win"
	GameOutcomeLoss GameOutcome = "loss"
	GameOutcomeDraw GameOutcome = "draw"
)

// GameResult describes what happened in a single Bedwars game — which
// gamemode it was played in, how it ended for the player, and the stat
// deltas that the player accrued during it.
type GameResult struct {
	Gamemode   Gamemode
	Outcome    GameOutcome
	FinalKills int
	FinalDeath bool
	BedsBroken int
	BedLost    bool
	Kills      int
	Deaths     int
	Experience int64
}
