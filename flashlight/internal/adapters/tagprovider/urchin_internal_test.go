package tagprovider

import (
	"context"
	"testing"

	"github.com/stretchr/testify/require"

	"github.com/Amund211/flashlight/internal/domain"
)

func TestTagsFromUrchinResponse(t *testing.T) {
	t.Parallel()

	ctx := context.Background()

	// The responses below are verbatim from real GET /v3/player/tags and
	// POST /v3/players responses (2026-08-01), except where a case is marked
	// synthetic.
	//
	// `displayname` is the formatted Hypixel name, including the rank prefix and its
	// plus-colors. We don't parse it today, but the cases below keep real prefixes
	// (MVP++, MVP+ in two different plus-colors, PIG+++, and no rank) so we have
	// samples if we ever do.
	//
	// NOTE: `uuid` is always anonymized. For tagged players, `added_by`,
	//       `added_by_username`, and the username part of `displayname` are replaced
	//       with placeholders too, to avoid pairing real identities with real
	//       cheating accusations in the repo - the rank prefix is left as urchin
	//       returned it. Untagged players keep their real `displayname` in full.
	//       `tag_type`, `reason`, `added_on`, `expires_at`, `hide_username`, and
	//       which fields are present at all, are always exactly as urchin returned
	//       them.
	cases := []struct {
		name     string
		response string
		tags     domain.Tags
		seen     urchinTagCollection
	}{
		{
			name: "confirmed cheater",
			response: `{
			  "uuid": "0123456789abcdef0123456789abcdef",
			  "displayname": "§b[MVP§f+§b] anonymized",
			  "tags": [
				{
				  "tag_type": "confirmed_cheater",
				  "reason": "Highjumping to Y=300, Longjumping 64 blocks, Autoblocking, Airstucking, Blinking, Not taking kb while mining bed through players, Boosted by Q14, Teleporting into players",
				  "added_by": 111111111111111111,
				  "added_by_username": "anonymized",
				  "added_on": 1769415379625,
				  "hide_username": false
				}
			  ]
			}`,
			tags: domain.Tags{}.AddCheating(domain.TagSeverityHigh),
			seen: urchinTagCollection{confirmedCheater: true},
		},
		{
			name: "blatant cheater",
			// This player has no rank, so the displayname is just the gray name.
			response: `{
			  "uuid": "0123456789abcdef0123456789abcdef",
			  "displayname": "§7anonymized",
			  "tags": [
				{
				  "tag_type": "blatant_cheater",
				  "reason": "blatant legit scaff, lagrange; possible ab, nuke, fastmine",
				  "added_by": 111111111111111111,
				  "added_by_username": "anonymized",
				  "added_on": 1766621381440,
				  "hide_username": false
				}
			  ]
			}`,
			tags: domain.Tags{}.AddCheating(domain.TagSeverityHigh),
			seen: urchinTagCollection{blatantCheater: true},
		},
		{
			name: "replays needed",
			response: `{
			  "uuid": "0123456789abcdef0123456789abcdef",
			  "displayname": "§6[MVP§d++§r§6] anonymized",
			  "tags": [
				{
				  "tag_type": "replays_needed",
				  "reason": "",
				  "added_by": 111111111111111111,
				  "added_by_username": "anonymized",
				  "added_on": 1785208595998,
				  "hide_username": false,
				  "expires_at": 1787022995996
				}
			  ]
			}`,
			// Marks a player as awaiting review, not as a finding, so it must not
			// affect the severities we report. This was the only tag in the sample
			// carrying an expires_at, and its reason was empty.
			tags: domain.Tags{},
			seen: urchinTagCollection{replaysNeeded: true},
		},
		{
			name: "sniper",
			// Tags from POST /v3/players, which returns no displayname.
			response: `{
			  "uuid": "0123456789abcdef0123456789abcdef",
			  "tags": [
				{
				  "tag_type": "sniper",
				  "reason": "ab legitscaff lagrange blink",
				  "added_by": 111111111111111111,
				  "added_by_username": "anonymized",
				  "added_on": 1760968222172,
				  "hide_username": false
				}
			  ]
			}`,
			tags: domain.Tags{}.AddSniping(domain.TagSeverityHigh).AddCheating(domain.TagSeverityMedium),
			seen: urchinTagCollection{sniper: true},
		},
		{
			name: "closet cheater",
			// Tags from POST /v3/players, which returns no displayname.
			response: `{
			  "uuid": "0123456789abcdef0123456789abcdef",
			  "tags": [
				{
				  "tag_type": "closet_cheater",
				  "reason": "legitscaff",
				  "added_by": 111111111111111111,
				  "added_by_username": "anonymized",
				  "added_on": 1755203361680,
				  "hide_username": false
				}
			  ]
			}`,
			tags: domain.Tags{}.AddCheating(domain.TagSeverityMedium),
			seen: urchinTagCollection{closetCheater: true},
		},
		{
			name: "hidden username omits added_by entirely",
			// Tags from POST /v3/players, which returns no displayname.
			response: `{
			  "uuid": "0123456789abcdef0123456789abcdef",
			  "tags": [
				{
				  "tag_type": "confirmed_cheater",
				  "reason": "legitscaff, timer in void, likely more",
				  "added_on": 1738980052864,
				  "hide_username": true
				}
			  ]
			}`,
			tags: domain.Tags{}.AddCheating(domain.TagSeverityHigh),
			seen: urchinTagCollection{confirmedCheater: true},
		},
		{
			name: "multiple tags",
			// NOTE: Synthetic - no player in the sample carried more than one tag, so
			//       this combines two real tags from different players.
			response: `{
			  "uuid": "0123456789abcdef0123456789abcdef",
			  "displayname": "§7anonymized",
			  "tags": [
				{
				  "tag_type": "closet_cheater",
				  "reason": "legitscaff",
				  "added_by": 111111111111111111,
				  "added_by_username": "anonymized",
				  "added_on": 1755203361680,
				  "hide_username": false
				},
				{
				  "tag_type": "replays_needed",
				  "reason": "",
				  "added_by": 111111111111111111,
				  "added_by_username": "anonymized",
				  "added_on": 1785208595998,
				  "hide_username": false,
				  "expires_at": 1787022995996
				}
			  ]
			}`,
			tags: domain.Tags{}.AddCheating(domain.TagSeverityMedium),
			seen: urchinTagCollection{closetCheater: true, replaysNeeded: true},
		},
		{
			name: "no tags, MVP+ with dark aqua plus",
			response: `{
			  "uuid": "0123456789abcdef0123456789abcdef",
			  "displayname": "§b[MVP§3+§b] Skydeath",
			  "tags": []
			}`,
			tags: domain.Tags{},
			seen: urchinTagCollection{},
		},
		{
			name: "no tags, special rank with no space before the name",
			response: `{
			  "uuid": "0123456789abcdef0123456789abcdef",
			  "displayname": "§d[PIG§b+++§d]Technoblade",
			  "tags": []
			}`,
			tags: domain.Tags{},
			seen: urchinTagCollection{},
		},
		{
			name: "player unknown to urchin",
			// Urchin returns 200 with no tags, and no displayname field at all, for a
			// well formed UUID it has never seen.
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
