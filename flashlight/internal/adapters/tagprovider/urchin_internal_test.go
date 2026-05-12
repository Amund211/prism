package tagprovider

import (
	"context"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/domain"
)

func TestScrubURLKey(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name string
		in   string
		want string
	}{
		{
			name: "key in url query",
			in:   `failed to send request: Get "https://urchin.ws/player/01234567-89ab-cdef-0123-456789abcdef?sources=MANUAL&key=super-secret-key": context deadline exceeded`,
			want: `failed to send request: Get "https://urchin.ws/player/01234567-89ab-cdef-0123-456789abcdef?sources=MANUAL&key=<redacted>": context deadline exceeded`,
		},
		{
			name: "no key",
			in:   `failed to send request: Get "https://urchin.ws/player/01234567-89ab-cdef-0123-456789abcdef?sources=MANUAL": context deadline exceeded`,
			want: `failed to send request: Get "https://urchin.ws/player/01234567-89ab-cdef-0123-456789abcdef?sources=MANUAL": context deadline exceeded`,
		},
		{
			name: "key as only query param",
			in:   `something key=hunter2 something else`,
			want: `something key=<redacted> something else`,
		},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			t.Parallel()
			require.Equal(t, c.want, scrubURLKey(c.in))
		})
	}
}

func TestTagsFromUrchinResponse(t *testing.T) {
	t.Parallel()

	ctx := context.Background()

	// All responses are real with anonymized UUIDs, except where noted
	cases := []struct {
		name     string
		response string
		tags     domain.Tags
		seen     urchinTagCollection
	}{
		{
			name: "sniper",
			response: `{
			  "uuid": "0123456789abcdef0123456789abcdef",
			  "tags": [
				{
				  "type": "sniper",
				  "reason": "3q - scaff, ab, blink",
				  "added_by_id": null,
				  "added_by_username": null,
				  "added_on": "2025-10-10T06:56:37.998405"
				}
			  ]
			}`,
			tags: domain.Tags{}.AddSniping(domain.TagSeverityHigh).AddCheating(domain.TagSeverityMedium),
			seen: urchinTagCollection{sniper: true},
		},
		{
			name: "confirmed cheater",
			response: `{
			  "uuid": "0123456789abcdef0123456789abcdef",
			  "tags": [
				{
				  "type": "confirmed_cheater",
				  "reason": "myau and vape user",
				  "added_by_id": null,
				  "added_by_username": null,
				  "added_on": "2025-02-04T23:07:17.395263"
				}
			  ]
			}`,
			tags: domain.Tags{}.AddCheating(domain.TagSeverityHigh),
			seen: urchinTagCollection{confirmedCheater: true},
		},
		{
			name: "blatant cheater",
			response: `{
			  "uuid": "0123456789abcdef0123456789abcdef",
			  "tags": [
				{
				  "type": "blatant_cheater",
				  "reason": "autblocking blinking nuking",
				  "added_by_id": null,
				  "added_by_username": null,
				  "added_on": "2025-10-17T09:23:34.448962"
				}
			  ]
			}`,
			tags: domain.Tags{}.AddCheating(domain.TagSeverityHigh),
			seen: urchinTagCollection{blatantCheater: true},
		},
		{
			name: "closet cheater",
			response: `{
			  "uuid": "0123456789abcdef0123456789abcdef",
			  "tags": [
				{
				  "type": "closet_cheater",
				  "reason": "legit scaff and velo",
				  "added_by_id": null,
				  "added_by_username": null,
				  "added_on": "2024-10-17T01:33:19.826840"
				}
			  ]
			}`,
			tags: domain.Tags{}.AddCheating(domain.TagSeverityMedium),
			seen: urchinTagCollection{closetCheater: true},
		},
		{
			name: "no tags",
			response: `{
			  "uuid": "0123456789abcdef0123456789abcdef",
			  "tags": []
			}`,
			tags: domain.Tags{},
			seen: urchinTagCollection{},
		},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			t.Parallel()
			tags, seen, err := tagsFromUrchinResponse(ctx, 200, []byte(c.response), false)
			require.NoError(t, err)

			require.Equal(t, c.tags, tags)

			// For metrics
			require.Equal(t, c.seen, seen)
		})
	}
}
