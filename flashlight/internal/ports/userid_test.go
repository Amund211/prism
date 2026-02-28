package ports_test

import (
	"net/http"
	"strings"
	"testing"

	"github.com/Amund211/flashlight/internal/ports"
	"github.com/stretchr/testify/require"
)

func TestGetUserID(t *testing.T) {
	t.Parallel()

	cases := []struct {
		uidHeader string
		userID    string
	}{
		// Standard user ids (uuid)
		{uidHeader: "743e61ad84344c4a995145763950b4bd", userID: "743e61ad84344c4a995145763950b4bd"},
		{uidHeader: "1025ff88-5234-4481-900b-f64ea190cf4e", userID: "1025ff88-5234-4481-900b-f64ea190cf4e"},
		// Custom user id
		{uidHeader: "my-id", userID: "my-id"},
		// Weird case
		{uidHeader: "", userID: "<missing>"},
		// User controlled input -> Long strings get truncated
		{uidHeader: strings.Repeat("1", 1000), userID: strings.Repeat("1", 50)},
	}
	for _, c := range cases {
		t.Run(c.uidHeader, func(t *testing.T) {
			t.Parallel()

			request := &http.Request{
				Header: http.Header{"X-User-Id": []string{c.uidHeader}},
			}
			require.Equal(t, c.userID, ports.GetUserID(request))
		})
	}
	t.Run("missing", func(t *testing.T) {
		t.Parallel()

		request := &http.Request{}
		require.Equal(t, "<missing>", ports.GetUserID(request))
	})
}
