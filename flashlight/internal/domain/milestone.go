package domain

// Gamemode represents different game modes
type Gamemode string

const (
	GamemodeOverall Gamemode = "overall"
)

// Stat represents different statistical measures
type Stat string

const (
	StatStars      Stat = "stars"
	StatExperience Stat = "experience"
)

// MilestoneAchievement represents when a milestone was reached
type MilestoneAchievement struct {
	Milestone int64                      // The milestone value that was reached
	After     *MilestoneAchievementStats // First stats after the milestone was reached
}

type MilestoneAchievementStats struct {
	Player PlayerPIT
	Value  int64
}
