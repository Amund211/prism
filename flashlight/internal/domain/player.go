package domain

import (
	"time"
)

type PlayerPIT struct {
	DBID *string

	QueriedAt time.Time

	UUID string

	Displayname *string
	LastLogin   *time.Time
	LastLogout  *time.Time

	// TODO: Remove? -> Can be derived from checking gamesplayed == 0
	MissingBedwarsStats bool

	Experience int64
	Solo       GamemodeStatsPIT
	Doubles    GamemodeStatsPIT
	Threes     GamemodeStatsPIT
	Fours      GamemodeStatsPIT
	Fourv4     GamemodeStatsPIT
	Overall    GamemodeStatsPIT
}

type GamemodeStatsPIT struct {
	// Winstreak is nil when hidden via Hypixel API settings. Usually all
	// gamemodes are set or all nil, but they vary independently: a gamemode
	// can be nil while others are set, and Overall can be nil while individual
	// gamemodes are set. Do not assume presence is consistent across gamemodes.
	Winstreak   *int
	GamesPlayed int
	Wins        int
	Losses      int
	BedsBroken  int
	BedsLost    int
	FinalKills  int
	FinalDeaths int
	Kills       int
	Deaths      int
}

// Stars calculates the player's stars based on their experience
func (p *PlayerPIT) Stars() float64 {
	return ExperienceToStars(p.Experience)
}
