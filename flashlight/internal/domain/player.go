package domain

import (
	"time"
)

type PlayerPIT struct {
	QueriedAt time.Time

	UUID string

	Displayname *string
	LastLogin   *time.Time
	LastLogout  *time.Time

	MissingBedwarsStats bool

	Experience float64
	Solo       GamemodeStatsPIT
	Doubles    GamemodeStatsPIT
	Threes     GamemodeStatsPIT
	Fours      GamemodeStatsPIT
	Overall    GamemodeStatsPIT
}

type GamemodeStatsPIT struct {
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
