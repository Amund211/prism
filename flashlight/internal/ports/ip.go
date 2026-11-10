package ports

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"net"
	"net/http"
	"strings"

	"github.com/Amund211/flashlight/internal/logging"
	"github.com/Amund211/flashlight/internal/reporting"
)

// Hard coded IP of the flashlight load balancer in GCP
const gcpLoadBalancerIP = "34.111.7.239"

type IP string

func (ip IP) String() string {
	return string(ip)
}

func (ip IP) Hash() string {
	hash := sha256.Sum256([]byte(ip))
	return hex.EncodeToString(hash[:])
}

func GetIP(r *http.Request) IP {
	ctx := r.Context()

	xff := r.Header.Get("X-Forwarded-For")
	if xff == "" {
		logging.FromContext(ctx).WarnContext(ctx, "X-Forwarded-For header missing")
		reporting.Report(
			ctx,
			fmt.Errorf("X-Forwarded-For header missing"),
			map[string]string{
				"headerXForwardedFor": xff,
				"remoteAddr":          r.RemoteAddr,
				"method":              r.Method,
				"userAgent":           r.UserAgent(),
				"url":                 r.URL.String(),
			},
		)

		return IP("<missing>")
	}

	// Two cases:
	// 1. Behind GCP Load Balancer:
	// > X-Forwarded-For header
	// > The load balancer appends two IP addresses to the X-Forwarded-For header, separated by a single comma, in the following order:
	// >     The IP address of the client that connects to the load balancer
	// >     The IP address of the load balancer's forwarding rule
	//
	// > If the incoming request does not include an X-Forwarded-For header, the resulting header is as follows:
	// > X-Forwarded-For: <client-ip>,<load-balancer-ip>
	//
	// > If the incoming request already includes an X-Forwarded-For header, the load balancer appends its values to the existing header:
	// > X-Forwarded-For: <existing-value>,<client-ip>,<load-balancer-ip>
	//
	// > Caution: The load balancer does not verify any IP addresses that precede <client-ip>,<load-balancer-ip> in this header. The preceding IP addresses might contain other characters, including spaces.

	// 2. Directly to Cloud Run: (run.app)
	// From testing this seems to behave the same way as the load balancer, except there's no load balancer IP appended.

	ips := strings.Split(xff, ",")

	if ips[len(ips)-1] == gcpLoadBalancerIP {
		// Case 1: Behind GCP Load Balancer
		// Remove the load balancer IP so we can treat the remaining value the same way as case 2
		ips = ips[:len(ips)-1]
	}

	if len(ips) == 0 {
		logging.FromContext(ctx).WarnContext(ctx, "Found no client IP in X-Forwarded-For header")
		reporting.Report(
			ctx,
			fmt.Errorf("found no client IP in X-Forwarded-For header"),
			map[string]string{
				"headerXForwardedFor": xff,
				"remoteAddr":          r.RemoteAddr,
				"method":              r.Method,
				"userAgent":           r.UserAgent(),
				"url":                 r.URL.String(),
			},
		)
		return IP("<missing>")
	}

	clientIP := ips[len(ips)-1]
	parsed := net.ParseIP(clientIP)
	if parsed == nil {
		logging.FromContext(ctx).WarnContext(ctx, "Failed to parse client IP from X-Forwarded-For header", "clientIP", clientIP)
		reporting.Report(
			ctx,
			fmt.Errorf("failed to parse client IP from X-Forwarded-For header"),
			map[string]string{
				"clientIP":            clientIP,
				"headerXForwardedFor": xff,
				"remoteAddr":          r.RemoteAddr,
				"method":              r.Method,
				"userAgent":           r.UserAgent(),
				"url":                 r.URL.String(),
			},
		)
		return IP("<invalid>")
	}

	return IP(parsed.String())
}
