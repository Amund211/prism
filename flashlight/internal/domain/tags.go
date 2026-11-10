package domain

import "fmt"

type TagSeverity int

const (
	TagSeverityNone TagSeverity = iota
	TagSeverityMedium
	TagSeverityHigh
)

func (ts TagSeverity) String() string {
	switch ts {
	case TagSeverityNone:
		return "none"
	case TagSeverityMedium:
		return "medium"
	case TagSeverityHigh:
		return "high"
	default:
		return fmt.Sprintf("<invalid tag severity>(%d)", int(ts))
	}
}

type Tags struct {
	Cheating TagSeverity
	Sniping  TagSeverity
}

func (t Tags) AddCheating(severity TagSeverity) Tags {
	if severity > t.Cheating {
		t.Cheating = severity
	}
	return t
}

func (t Tags) AddSniping(severity TagSeverity) Tags {
	if severity > t.Sniping {
		t.Sniping = severity
	}
	return t
}
