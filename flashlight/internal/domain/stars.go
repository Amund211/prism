package domain

const expPerPrestige = (500 + 1000 + 2000 + 3500 + (5000 * 96))

func StarsToExperience(stars int) int64 {
	prestiges := int64(stars / 100)
	stars = stars % 100

	exp := prestiges * expPerPrestige
	for star := 1; star <= stars; star++ {
		expForStar := 5000
		switch star {
		case 1:
			expForStar = 500
		case 2:
			expForStar = 1000
		case 3:
			expForStar = 2000
		case 4:
			expForStar = 3500
		}

		exp += int64(expForStar)

	}

	return exp
}

func ExperienceToStars(experience int64) int {
	prestiges := int(experience / expPerPrestige)
	remainingExperience := int(experience % expPerPrestige)

	stars := prestiges * 100
	for star := 1; star <= 100; star++ {
		expForStar := 5000
		switch star {
		case 1:
			expForStar = 500
		case 2:
			expForStar = 1000
		case 3:
			expForStar = 2000
		case 4:
			expForStar = 3500
		}

		if remainingExperience < expForStar {
			break
		}

		remainingExperience -= expForStar
		stars++
	}

	return stars
}
