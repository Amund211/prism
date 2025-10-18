package domain

const expPerPrestige = (500 + 1000 + 2000 + 3500 + (5000 * 96))

func expUntilNextStar(star int) int {
	switch star % 100 {
	case 0:
		return 500
	case 1:
		return 1000
	case 2:
		return 2000
	case 3:
		return 3500
	default:
		return 5000
	}
}

func StarsToExperience(stars int) int64 {
	prestiges := int64(stars / 100)
	stars = stars % 100

	exp := prestiges * expPerPrestige
	for star := range stars {
		exp += int64(expUntilNextStar(star))
	}

	return exp
}

func ExperienceToStars(experience int64) int {
	prestiges := int(experience / expPerPrestige)
	remainingExperience := int(experience % expPerPrestige)

	stars := prestiges * 100
	for star := range 100 {
		if remainingExperience < expUntilNextStar(star) {
			break
		}

		remainingExperience -= expUntilNextStar(star)
		stars++
	}

	return stars
}
