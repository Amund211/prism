package domain

type Session struct {
	Start       PlayerPIT
	End         PlayerPIT
	Consecutive bool
	// Ongoing is true iff this session could be extended.
	Ongoing bool
}
