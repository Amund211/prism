package ports

import (
	"net/url"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/domain"
)

const testChallenge = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"

func TestParseMicrosoftSignInTarget(t *testing.T) {
	t.Parallel()

	origins, err := NewDomainSuffixes("prismoverlay.com", "rainbow-ctx.pages.dev")
	require.NoError(t, err)

	parse := func(raw string) (*domain.MicrosoftSignInTarget, error) {
		query, err := url.ParseQuery(raw)
		require.NoError(t, err)
		return parseMicrosoftSignInTarget(query, origins)
	}
	withReturn := func(ret string) string {
		return "return=" + url.QueryEscape(ret) + "&challenge=" + testChallenge
	}

	t.Run("no return is the test sign-in", func(t *testing.T) {
		t.Parallel()
		target, err := parse("")
		require.NoError(t, err)
		require.Nil(t, target)
	})

	for _, tc := range []struct {
		name  string
		query string
		want  domain.MicrosoftSignInTarget
	}{
		{"prod origin", withReturn("https://prismoverlay.com"), domain.MicrosoftSignInTarget{ClientType: domain.MicrosoftClientRainbow, URL: "https://prismoverlay.com", Challenge: testChallenge}},
		{"prod subdomain", withReturn("https://www.prismoverlay.com"), domain.MicrosoftSignInTarget{ClientType: domain.MicrosoftClientRainbow, URL: "https://www.prismoverlay.com", Challenge: testChallenge}},
		{"staging preview", withReturn("https://abc123.rainbow-ctx.pages.dev"), domain.MicrosoftSignInTarget{ClientType: domain.MicrosoftClientRainbow, URL: "https://abc123.rainbow-ctx.pages.dev", Challenge: testChallenge}},
		{"ipv4 loopback", withReturn("http://127.0.0.1:52345/callback") + "&state=nonce_-1", domain.MicrosoftSignInTarget{ClientType: domain.MicrosoftClientPrism, URL: "http://127.0.0.1:52345/callback", Challenge: testChallenge, ClientState: "nonce_-1"}},
		{"ipv6 loopback", withReturn("http://[::1]:52345/callback"), domain.MicrosoftSignInTarget{ClientType: domain.MicrosoftClientPrism, URL: "http://[::1]:52345/callback", Challenge: testChallenge}},
		{"longest state", withReturn("http://127.0.0.1:1/callback") + "&state=" + strings.Repeat("n", 128), domain.MicrosoftSignInTarget{ClientType: domain.MicrosoftClientPrism, URL: "http://127.0.0.1:1/callback", Challenge: testChallenge, ClientState: strings.Repeat("n", 128)}},
	} {
		t.Run("accepts "+tc.name, func(t *testing.T) {
			t.Parallel()
			target, err := parse(tc.query)
			require.NoError(t, err)
			require.NotNil(t, target)
			require.Equal(t, tc.want, *target)
		})
	}

	for name, ret := range map[string]string{
		"empty":                  "",
		"trailing slash":         "https://prismoverlay.com/",
		"a path":                 "https://prismoverlay.com/session",
		"a query":                "https://prismoverlay.com?x=1",
		"empty query":            "https://prismoverlay.com?",
		"a fragment":             "https://prismoverlay.com#x",
		"a port":                 "https://prismoverlay.com:443",
		"userinfo":               "https://user@prismoverlay.com",
		"http rainbow":           "http://prismoverlay.com",
		"other site":             "https://evil.com",
		"suffix lookalike":       "https://evilprismoverlay.com",
		"suffix as subdomain":    "https://prismoverlay.com.evil.com",
		"uppercase host":         "https://PRISMOVERLAY.COM",
		"scheme-relative":        "//prismoverlay.com",
		"javascript":             "javascript:alert(1)",
		"localhost":              "http://localhost:52345/callback",
		"https loopback":         "https://127.0.0.1:52345/callback",
		"loopback lookalike":     "http://127.0.0.1.evil.com:52345/callback",
		"loopback userinfo":      "http://127.0.0.1@evil.com/callback",
		"loopback userinfo port": "http://127.0.0.1:52345@evil.com/callback",
		"octal loopback":         "http://0177.0.0.1:52345/callback",
		"integer loopback":       "http://2130706433:52345/callback",
		"other 127/8":            "http://127.0.0.2:52345/callback",
		"mapped v6 loopback":     "http://[::ffff:127.0.0.1]:52345/callback",
		"long v6 loopback":       "http://[0:0:0:0:0:0:0:1]:52345/callback",
		"private ip":             "http://192.168.1.2:52345/callback",
		"no port":                "http://127.0.0.1/callback",
		"empty port":             "http://127.0.0.1:/callback",
		"port zero":              "http://127.0.0.1:0/callback",
		"port too big":           "http://127.0.0.1:65536/callback",
		"loopback other path":    "http://127.0.0.1:52345/other",
		"loopback no path":       "http://127.0.0.1:52345",
		"loopback encoded path":  "http://127.0.0.1:52345/%63allback",
		"loopback trailing":      "http://127.0.0.1:52345/callback/",
		"loopback query":         "http://127.0.0.1:52345/callback?x=1",
		"loopback empty query":   "http://127.0.0.1:52345/callback?",
		"loopback fragment":      "http://127.0.0.1:52345/callback#x",
		"over the length cap":    "https://" + strings.Repeat("a", 250) + ".prismoverlay.com",
	} {
		t.Run("refuses return "+name, func(t *testing.T) {
			t.Parallel()
			_, err := parse(withReturn(ret))
			require.Error(t, err)
		})
	}

	for name, query := range map[string]string{
		"two returns":            withReturn("https://prismoverlay.com") + "&return=https%3A%2F%2Fevil.com",
		"no challenge":           "return=" + url.QueryEscape("https://prismoverlay.com"),
		"empty challenge":        "return=" + url.QueryEscape("https://prismoverlay.com") + "&challenge=",
		"short challenge":        "return=" + url.QueryEscape("https://prismoverlay.com") + "&challenge=" + testChallenge[1:],
		"long challenge":         withReturn("https://prismoverlay.com") + "x",
		"padded challenge":       "return=" + url.QueryEscape("https://prismoverlay.com") + "&challenge=" + testChallenge[1:] + "%3D",
		"non-base64url":          "return=" + url.QueryEscape("https://prismoverlay.com") + "&challenge=" + testChallenge[1:] + "%2B",
		"two challenges":         withReturn("https://prismoverlay.com") + "&challenge=" + testChallenge,
		"challenge alone":        "challenge=" + testChallenge,
		"state alone":            "state=nonce",
		"state on rainbow":       withReturn("https://prismoverlay.com") + "&state=nonce",
		"empty prism state":      withReturn("http://127.0.0.1:52345/callback") + "&state=",
		"two prism states":       withReturn("http://127.0.0.1:52345/callback") + "&state=a&state=b",
		"prism state too long":   withReturn("http://127.0.0.1:52345/callback") + "&state=" + strings.Repeat("n", 129),
		"prism state bad chars":  withReturn("http://127.0.0.1:52345/callback") + "&state=a%26b",
		"prism state with space": withReturn("http://127.0.0.1:52345/callback") + "&state=a+b",
	} {
		t.Run("refuses "+name, func(t *testing.T) {
			t.Parallel()
			_, err := parse(query)
			require.Error(t, err)
		})
	}

	t.Run("errors never quote the input", func(t *testing.T) {
		t.Parallel()
		_, err := parse(withReturn("https://evil.com") + "&state=secret-nonce")
		require.Error(t, err)
		require.NotContains(t, err.Error(), "evil.com")
		require.NotContains(t, err.Error(), testChallenge)
		require.NotContains(t, err.Error(), "secret-nonce")
	})
}
