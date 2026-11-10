package ports

import (
	"errors"
	"fmt"
	"net"
	"net/url"
	"regexp"
	"strconv"

	"github.com/Amund211/flashlight/internal/domain"
)

// challengeRx is base64url(sha256(verifier)), unpadded.
var challengeRx = regexp.MustCompile(`^[A-Za-z0-9_-]{43}$`)

var clientStateRx = regexp.MustCompile(fmt.Sprintf(`^[A-Za-z0-9_-]{1,%d}$`, domain.MicrosoftSignInClientStateMaxLength))

// prismCallbackPath is the only path prism's loopback listener serves.
const prismCallbackPath = "/callback"

// errInvalidSignInTarget never quotes the input: return, challenge and
// state are the client's.
var errInvalidSignInTarget = errors.New("invalid sign-in target")

// parseMicrosoftSignInTarget validates /start's return, challenge and
// state. No return is the test sign-in (nil). The return is where the
// result token goes, so a loose check here is a token-exfiltration
// primitive.
func parseMicrosoftSignInTarget(query url.Values, rainbowOrigins *DomainSuffixes) (*domain.MicrosoftSignInTarget, error) {
	if !query.Has("return") {
		if query.Has("challenge") || query.Has("state") {
			return nil, fmt.Errorf("%w: challenge or state without return", errInvalidSignInTarget)
		}
		return nil, nil
	}

	ret, ok := single(query, "return")
	if !ok || ret == "" || len(ret) > domain.MicrosoftSignInReturnMaxLength {
		return nil, fmt.Errorf("%w: return is missing, repeated or too long", errInvalidSignInTarget)
	}
	challenge, ok := single(query, "challenge")
	if !ok || !challengeRx.MatchString(challenge) {
		return nil, fmt.Errorf("%w: challenge is missing, repeated or malformed", errInvalidSignInTarget)
	}

	u, err := url.Parse(ret)
	if err != nil {
		return nil, fmt.Errorf("%w: return is not a url", errInvalidSignInTarget)
	}
	if u.User != nil || u.Opaque != "" || u.RawQuery != "" || u.ForceQuery || u.Fragment != "" || u.RawFragment != "" {
		return nil, fmt.Errorf("%w: return has userinfo, a query or a fragment", errInvalidSignInTarget)
	}

	switch u.Scheme {
	case "https":
		if query.Has("state") {
			return nil, fmt.Errorf("%w: state is for prism only", errInvalidSignInTarget)
		}
		if u.Port() != "" || u.Path != "" || ret != "https://"+u.Host || !rainbowOrigins.AnyMatch(ret) {
			return nil, fmt.Errorf("%w: return is not an allowed rainbow origin", errInvalidSignInTarget)
		}
		return &domain.MicrosoftSignInTarget{
			ClientType: domain.MicrosoftClientRainbow,
			URL:        ret,
			Challenge:  challenge,
		}, nil

	case "http":
		if !isLoopbackLiteral(u.Hostname()) {
			return nil, fmt.Errorf("%w: return host is not a loopback literal", errInvalidSignInTarget)
		}
		port, err := strconv.Atoi(u.Port())
		if err != nil || port < 1 || port > 65535 {
			return nil, fmt.Errorf("%w: return port is invalid", errInvalidSignInTarget)
		}
		if u.EscapedPath() != prismCallbackPath {
			return nil, fmt.Errorf("%w: return path is not %s", errInvalidSignInTarget, prismCallbackPath)
		}
		clientState := ""
		if query.Has("state") {
			clientState, ok = single(query, "state")
			if !ok || !clientStateRx.MatchString(clientState) {
				return nil, fmt.Errorf("%w: state is repeated or malformed", errInvalidSignInTarget)
			}
		}
		return &domain.MicrosoftSignInTarget{
			ClientType:  domain.MicrosoftClientPrism,
			URL:         (&url.URL{Scheme: "http", Host: net.JoinHostPort(u.Hostname(), strconv.Itoa(port)), Path: prismCallbackPath}).String(),
			Challenge:   challenge,
			ClientState: clientState,
		}, nil

	default:
		return nil, fmt.Errorf("%w: return scheme is not http or https", errInvalidSignInTarget)
	}
}

// isLoopbackLiteral accepts exactly 127.0.0.1 and ::1, in canonical form.
// The canonical-form check refuses ::ffff:127.0.0.1 and long forms of ::1,
// which net.IP.Equal would call equal.
func isLoopbackLiteral(host string) bool {
	ip := net.ParseIP(host)
	if ip == nil || ip.String() != host {
		return false
	}
	return ip.Equal(net.IPv4(127, 0, 0, 1)) || ip.Equal(net.IPv6loopback)
}

func single(query url.Values, key string) (string, bool) {
	values := query[key]
	if len(values) != 1 {
		return "", false
	}
	return values[0], true
}
