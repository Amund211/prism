package domain

import "strings"

// IsValidUsername matches the names Mojang's lookup accepts, which is looser
// than current rules (3-16, [A-Za-z0-9_]) so that legacy names still pass.
func IsValidUsername(username string) bool {
	if len(username) == 0 || len(username) > 25 {
		return false
	}
	for i := range len(username) {
		c := username[i]
		if c < 0x20 || c > 0x7e {
			return false
		}
	}
	return !strings.ContainsAny(username, `#&/\`)
}
