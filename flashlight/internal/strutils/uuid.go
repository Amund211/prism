package strutils

import (
	"fmt"
	"strings"
	"unicode"
)

const validHexDigits = "0123456789abcdefABCDEF"

const dashedUUIDLength = 36

// Converts the input string to a dashed, lowercase UUID string
func NormalizeUUID(uuid string) (string, error) {
	normalized := stringBuilderWithCapacity(dashedUUIDLength)

	for _, char := range uuid {
		normLen := normalized.Len()
		if normLen == 8 || normLen == 13 || normLen == 18 || normLen == 23 {
			// Insert dashes at the appropriate indicies
			_, err := normalized.WriteRune('-')
			if err != nil {
				return "", fmt.Errorf("failed writing - to stringbuilder: %w", err)
			}
		}
		if char == '-' {
			continue
		} else if strings.ContainsRune(validHexDigits, char) {
			_, err := normalized.WriteRune(unicode.ToLower(char))
			if err != nil {
				return "", fmt.Errorf("failed writing to stringbuilder: %w", err)
			}
		} else {
			return "", fmt.Errorf("invalid character in UUID. input: '%s'", uuid)
		}
	}
	if normalized.Len() != dashedUUIDLength {
		return "", fmt.Errorf("normalized UUID has incorrect length. input: '%s'", uuid)
	}
	return normalized.String(), nil
}

func UUIDIsNormalized(uuid string) bool {
	normalizedUUID, err := NormalizeUUID(uuid)
	if err != nil {
		return false
	}
	return normalizedUUID == uuid
}

func stringBuilderWithCapacity(capacity int) *strings.Builder {
	var sb strings.Builder

	missingCap := capacity - sb.Cap()

	if missingCap > 0 {
		sb.Grow(missingCap)
	}

	return &sb
}
