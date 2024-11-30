package strutils

import (
	"fmt"
	"strings"
	"unicode"
)

const VALID_HEX_DIGITS = "0123456789abcdefABCDEF"

const STRIPPED_UUID_LENGTH = 32

// Removes dashes and converts all characters to lowercase
func NormalizeUUID(uuid string) (string, error) {
	var normalized strings.Builder
	builderCap := normalized.Cap()
	missingCap := STRIPPED_UUID_LENGTH - builderCap
	if missingCap > 0 {
		normalized.Grow(missingCap)
	}

	for _, char := range uuid {
		if char == '-' {
			continue
		} else if strings.ContainsRune(VALID_HEX_DIGITS, char) {
			_, err := normalized.WriteRune(unicode.ToLower(char))
			if err != nil {
				return "", fmt.Errorf("failed writing to stringbuilder: %w", err)
			}
		} else {
			return "", fmt.Errorf("invalid character in UUID. input: '%s'", uuid)
		}
	}
	if normalized.Len() != STRIPPED_UUID_LENGTH {
		return "", fmt.Errorf("normalized UUID has incorrect length. input: '%s'", uuid)
	}
	return normalized.String(), nil
}
