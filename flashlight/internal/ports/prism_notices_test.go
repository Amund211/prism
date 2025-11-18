package ports_test

import (
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Amund211/flashlight/internal/domaintest"
	"github.com/Amund211/flashlight/internal/ports"
	"github.com/stretchr/testify/require"
)

func TestPrismNoticesHandler(t *testing.T) {
	t.Parallel()

	cases := []struct {
		userID       string
		prismVersion string
		responseJSON string
	}{
		{
			userID:       "",
			prismVersion: "",
			responseJSON: `{"notices":[]}`,
		},
		{
			userID:       domaintest.NewUUID(t),
			prismVersion: "v1.10.1-dev",
			responseJSON: `{"notices":[]}`,
		},
		{
			userID:       domaintest.NewUUID(t),
			prismVersion: "v1.11.0",
			responseJSON: `{"notices":[]}`,
		},
	}

	testLogger := slog.New(slog.NewTextHandler(io.Discard, nil))
	noopMiddleware := func(h http.HandlerFunc) http.HandlerFunc {
		return func(w http.ResponseWriter, r *http.Request) {
			h(w, r)
		}
	}

	for _, tc := range cases {
		name := fmt.Sprintf("version='%s' userID='%s'", tc.prismVersion, tc.userID)
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			handler := ports.MakePrismNoticesHandler(testLogger, noopMiddleware)

			req := httptest.NewRequest("GET", "/v1/prism-notices", nil)
			req.Header.Set("X-User-Id", tc.userID)
			req.Header.Set("X-Prism-Version", tc.prismVersion)

			w := httptest.NewRecorder()

			handler.ServeHTTP(w, req)

			require.Equal(t, http.StatusOK, w.Code)
			require.JSONEq(t, tc.responseJSON, w.Body.String())
			require.Equal(t, "application/json", w.Result().Header.Get("Content-Type"))
		})
	}
}
