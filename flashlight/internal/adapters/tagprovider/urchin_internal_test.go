package tagprovider

import (
	"context"
	"testing"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/stretchr/testify/require"
)

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
			name:     "sniper",
			response: `{"uuid":"0123456789abcdef0123456789abcdef","tags":[{"type":"sniper","reason":"3q - scaff, ab, blink","added_by_id":null,"added_by_username":null,"added_on":"2025-10-10T06:56:37.998405"}]}`,
			tags:     domain.Tags{}.AddSniping(domain.TagSeverityHigh).AddCheating(domain.TagSeverityMedium),
			seen:     urchinTagCollection{sniper: true},
		},
		{
			name:     "confirmed cheater",
			response: `{"uuid":"0123456789abcdef0123456789abcdef","tags":[{"type":"confirmed_cheater","reason":"myau and vape user","added_by_id":null,"added_by_username":null,"added_on":"2025-02-04T23:07:17.395263"}]}`,
			tags:     domain.Tags{}.AddCheating(domain.TagSeverityHigh),
			seen:     urchinTagCollection{confirmedCheater: true},
		},
		{
			name:     "no tags",
			response: `{"uuid":"0123456789abcdef0123456789abcdef","tags":[]}`,
			tags:     domain.Tags{},
			seen:     urchinTagCollection{},
		},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			t.Parallel()
			tags, seen, err := tagsFromUrchinResponse(ctx, 200, []byte(c.response))
			require.NoError(t, err)

			require.Equal(t, c.tags, tags)

			// For metrics
			require.Equal(t, c.seen, seen)
		})
	}
}
