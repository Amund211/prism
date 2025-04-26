package ports_test

import (
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/Amund211/flashlight/internal/ports"
	"github.com/stretchr/testify/require"
)

const PROD_DOMAIN_SUFFIX = "prismoverlay.com"
const STAGING_DOMAIN_SUFFIX = "rainbow-ctx.pages.dev"

type originRule struct {
	origin  string
	allowed bool
}

func TestCORS(t *testing.T) {
	t.Parallel()
	allowedOrigins, err := ports.NewDomainSuffixes(
		PROD_DOMAIN_SUFFIX,
		STAGING_DOMAIN_SUFFIX,
	)
	require.NoError(t, err)

	cases := []originRule{
		// Prod
		{
			origin: "https://prismoverlay.com",

			allowed: true,
		},
		{
			origin:  "https://www.prismoverlay.com",
			allowed: true,
		},
		// Staging
		{
			origin:  "https://53bcd591.rainbow-ctx.pages.dev",
			allowed: true,
		},
		{
			origin:  "https://new-api.rainbow-ctx.pages.dev",
			allowed: true,
		},
		{
			origin:  "https://rainbow-ctx.pages.dev",
			allowed: true,
		},
		// Other pages
		{
			origin:  "example.com",
			allowed: false,
		},
		{
			origin:  "https://example.com",
			allowed: false,
		},
		{
			origin:  "https://www.example.com",
			allowed: false,
		},
		{
			origin:  "https://www.google.com",
			allowed: false,
		},
		{
			origin:  "https://hypixel.net",
			allowed: false,
		},
		// Similar-looking domains
		{
			origin: "https://prism-overlay.com",

			allowed: false,
		},
		{
			origin:  "https://www.prism-overlay.com",
			allowed: false,
		},
		{
			origin: "https://myprismoverlay.com",

			allowed: false,
		},
		{
			origin:  "https://www.myprismoverlay.com",
			allowed: false,
		},
		{
			origin:  "https://superrainbow-ctx.pages.dev",
			allowed: false,
		},
		{
			origin:  "https://something.otherrainbow-ctx.pages.dev",
			allowed: false,
		},
		// Weird cases
		{
			origin:  "",
			allowed: false,
		},
		{
			origin:  "prismoverlay",
			allowed: false,
		},
		{
			origin:  "overlay.com",
			allowed: false,
		},
		{
			origin:  "prism.overlay.com",
			allowed: false,
		},
		{
			origin:  "prism-overlay.com",
			allowed: false,
		},
		{
			origin:  "pages.dev",
			allowed: false,
		},
		{
			origin:  "superrainbow-ctx.pages.dev",
			allowed: false,
		},
	}

	runCORSTest := func(t *testing.T, handler http.HandlerFunc, method string, c originRule, handlerStatusCode int, handlerBody []byte) {
		req := httptest.NewRequest(method, "https://api-url.com", nil)
		req.Header.Set("Origin", c.origin)
		w := httptest.NewRecorder()

		handler(w, req)

		resp := w.Result()

		// The handler is allowed to run when the method is not OPTIONS
		if method != "OPTIONS" {
			require.Equal(t, handlerStatusCode, resp.StatusCode)
			body, err := io.ReadAll(resp.Body)
			require.NoError(t, err)
			require.Equal(t, handlerBody, body)
		}

		// CORS
		if c.allowed {
			require.Equal(t, c.origin, resp.Header.Get("Access-Control-Allow-Origin"))

			if method == "OPTIONS" {
				require.Equal(t, "GET,POST", resp.Header.Get("Access-Control-Allow-Methods"))
				require.Equal(t, "Content-Type", resp.Header.Get("Access-Control-Allow-Headers"))
			} else {
				require.Empty(t, resp.Header.Get("Access-Control-Allow-Methods"))
				require.Empty(t, resp.Header.Get("Access-Control-Allow-Headers"))
			}
		} else {
			require.Empty(t, resp.Header.Get("Access-Control-Allow-Origin"))
			require.Empty(t, resp.Header.Get("Access-Control-Allow-Methods"))
			require.Empty(t, resp.Header.Get("Access-Control-Allow-Headers"))
		}
	}

	t.Run("BuildCORSMiddleware", func(t *testing.T) {
		middleware := ports.BuildCORSMiddleware(allowedOrigins)

		handler := middleware(
			func(w http.ResponseWriter, r *http.Request) {
				w.Write([]byte("Hello, world!"))
				w.WriteHeader(200)
			},
		)

		for _, c := range cases {
			t.Run(fmt.Sprintf("Origin:'%s'", c.origin), func(t *testing.T) {
				t.Parallel()
				for _, method := range []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"} {
					t.Run(method, func(t *testing.T) {
						t.Parallel()

						runCORSTest(t, handler, method, c, 200, []byte("Hello, world!"))
					})
				}
			})
		}
	})

	t.Run("BuildCORSHandler", func(t *testing.T) {
		handler := ports.BuildCORSHandler(allowedOrigins)

		for _, c := range cases {
			t.Run(fmt.Sprintf("Origin:'%s'", c.origin), func(t *testing.T) {
				t.Parallel()
				for _, method := range []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"} {
					t.Run(method, func(t *testing.T) {
						t.Parallel()

						runCORSTest(t, handler, method, c, 204, []byte{})
					})
				}
			})
		}
	})
}
