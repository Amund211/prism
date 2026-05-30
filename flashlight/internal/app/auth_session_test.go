package app_test

import (
	"strings"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/app"
)

func TestGenerateAuthSessionID(t *testing.T) {
	t.Parallel()
	id1, err := app.GenerateAuthSessionID()
	require.NoError(t, err)
	id2, err := app.GenerateAuthSessionID()
	require.NoError(t, err)
	// Pin the wire format with a literal so this test fails if the
	// production prefix ever drifts away from "flsess_" — independent
	// of whether the test-local mirror happens to be in lockstep.
	require.True(t, strings.HasPrefix(id1, "flsess_"),
		"session ids must start with the literal flsess_ prefix")
	require.True(t, strings.HasPrefix(id2, "flsess_"),
		"session ids must start with the literal flsess_ prefix")
	require.True(t, strings.HasPrefix(id1, sessionIDPrefix))
	require.True(t, strings.HasPrefix(id2, sessionIDPrefix))
	require.NotEqual(t, id1, id2)
	// prefix + base64-encoded 32 bytes = 7 + 43 = 50 chars
	require.Len(t, id1, len(sessionIDPrefix)+43)
}
