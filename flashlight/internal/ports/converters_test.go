package ports_test

import (
	"context"
	"fmt"
	"os"
	"path"
	"testing"
	"time"

	"github.com/Amund211/flashlight/internal/adapters/playerprovider"
	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/ports"
	"github.com/Amund211/flashlight/internal/strutils"

	"github.com/stretchr/testify/require"
)

const hypixelAPIResponsesDir = "../../fixtures/hypixel_api_responses/"
const expectedMinifiedDataDir = "testdata/expected_hypixel_style_responses/"

func ptr[T any](v T) *T {
	return &v
}

type playerToHypixelAPIResponseTestCase struct {
	name   string
	player *domain.PlayerPIT
	result []byte
}

func runPlayerToHypixelAPIResponseTest(t *testing.T, test playerToHypixelAPIResponseTestCase) {
	t.Helper()

	result, err := ports.PlayerToHypixelAPIResponseData(test.player)
	require.NoError(t, err)
	require.JSONEq(t, string(test.result), string(result))
}

func TestPlayerToHypixelAPIResponse(t *testing.T) {
	t.Parallel()

	queriedAt := time.Now()

	timePtr := func(timeStr string) *time.Time {
		timeTime, err := time.Parse(time.RFC3339, timeStr)
		require.NoError(t, err)
		return &timeTime
	}

	t.Run("literal cases", func(t *testing.T) {
		cases := []playerToHypixelAPIResponseTestCase{
			{
				name:   "no player",
				player: nil,
				result: []byte(`{"success": true, "player": null}`),
			},
			{
				name: "most fields",
				player: &domain.PlayerPIT{
					QueriedAt: queriedAt,

					UUID: "12345678-90ab-cdef-1234-567890abcdef",

					Displayname: ptr("TestPlayer"),
					LastLogin:   timePtr("2023-01-01T00:00:00Z"),
					LastLogout:  timePtr("2023-01-01T10:00:00Z"),

					MissingBedwarsStats: false,

					Experience: 1_087_000,
					Solo: domain.GamemodeStatsPIT{
						Winstreak:   ptr(0),
						GamesPlayed: 1,
						Wins:        2,
						Losses:      3,
						BedsBroken:  3,
						BedsLost:    4,
						FinalKills:  6,
						FinalDeaths: 7,
						Kills:       8,
						Deaths:      9,
					},
					Doubles: domain.GamemodeStatsPIT{
						Winstreak:   ptr(100),
						GamesPlayed: 101,
						Wins:        102,
						Losses:      103,
						BedsBroken:  104,
						BedsLost:    105,
						FinalKills:  106,
						FinalDeaths: 107,
						Kills:       108,
						Deaths:      109,
					},
					Threes: domain.GamemodeStatsPIT{
						Winstreak:   ptr(20),
						GamesPlayed: 201,
						Wins:        202,
						Losses:      203,
						BedsBroken:  204,
						BedsLost:    205,
						FinalKills:  206,
						FinalDeaths: 207,
						Kills:       208,
						Deaths:      209,
					},
					Fours: domain.GamemodeStatsPIT{
						Winstreak:   ptr(300),
						GamesPlayed: 301,
						Wins:        302,
						Losses:      303,
						BedsBroken:  304,
						BedsLost:    305,
						FinalKills:  306,
						FinalDeaths: 307,
						Kills:       308,
						Deaths:      309,
					},
					Overall: domain.GamemodeStatsPIT{
						Winstreak:   ptr(400),
						GamesPlayed: 401,
						Wins:        402,
						Losses:      403,
						BedsBroken:  404,
						BedsLost:    405,
						FinalKills:  406,
						FinalDeaths: 407,
						Kills:       408,
						Deaths:      409,
					},
				},
				result: []byte(`{
					"success": true,
					"player": {
						"uuid": "12345678-90ab-cdef-1234-567890abcdef",
						"displayname": "TestPlayer",
						"lastLogin":   1672531200000,
						"lastLogout":  1672567200000,
						"stats": {
							"Bedwars": {
								"Experience":                       1087000,
								"eight_one_winstreak":              0,
								"eight_one_games_played_bedwars":   1,
								"eight_one_wins_bedwars":           2,
								"eight_one_losses_bedwars":         3,
								"eight_one_beds_broken_bedwars":    3,
								"eight_one_beds_lost_bedwars":      4,
								"eight_one_final_kills_bedwars":    6,
								"eight_one_final_deaths_bedwars":   7,
								"eight_one_kills_bedwars":          8,
								"eight_one_deaths_bedwars":         9,
								"eight_two_winstreak":              100,
								"eight_two_games_played_bedwars":   101,
								"eight_two_wins_bedwars":           102,
								"eight_two_losses_bedwars":         103,
								"eight_two_beds_broken_bedwars":    104,
								"eight_two_beds_lost_bedwars":      105,
								"eight_two_final_kills_bedwars":    106,
								"eight_two_final_deaths_bedwars":   107,
								"eight_two_kills_bedwars":          108,
								"eight_two_deaths_bedwars":         109,
								"four_three_winstreak":             20,
								"four_three_games_played_bedwars":  201,
								"four_three_wins_bedwars":          202,
								"four_three_losses_bedwars":        203,
								"four_three_beds_broken_bedwars":   204,
								"four_three_beds_lost_bedwars":     205,
								"four_three_final_kills_bedwars":   206,
								"four_three_final_deaths_bedwars":  207,
								"four_three_kills_bedwars":         208,
								"four_three_deaths_bedwars":        209,
								"four_four_winstreak":              300,
								"four_four_games_played_bedwars":   301,
								"four_four_wins_bedwars":           302,
								"four_four_losses_bedwars":         303,
								"four_four_beds_broken_bedwars":    304,
								"four_four_beds_lost_bedwars":      305,
								"four_four_final_kills_bedwars":    306,
								"four_four_final_deaths_bedwars":   307,
								"four_four_kills_bedwars":          308,
								"four_four_deaths_bedwars":         309,
								"winstreak":                        400,
								"games_played_bedwars":             401,
								"wins_bedwars":                     402,
								"losses_bedwars":                   403,
								"beds_broken_bedwars":              404,
								"beds_lost_bedwars":                405,
								"final_kills_bedwars":              406,
								"final_deaths_bedwars":             407,
								"kills_bedwars":                    408,
								"deaths_bedwars":                   409
							}
						}
					}
				}`),
			},
			{
				name: "missing bedwars stats",
				player: &domain.PlayerPIT{
					QueriedAt: queriedAt,

					UUID: "12345678-90ab-cdef-1234-567890abcdef",

					Displayname: ptr("Player2"),
					LastLogin:   timePtr("2024-05-09T12:14:29Z"),
					LastLogout:  timePtr("2024-05-09T13:28:10Z"),

					// NOTE: Does nothing atm
					MissingBedwarsStats: true,

					Experience: 500,
					Solo:       domain.GamemodeStatsPIT{},
					Doubles:    domain.GamemodeStatsPIT{},
					Threes:     domain.GamemodeStatsPIT{},
					Fours:      domain.GamemodeStatsPIT{},
					Overall:    domain.GamemodeStatsPIT{},
				},
				result: []byte(`{
					"success": true,
					"player": {
						"uuid":"12345678-90ab-cdef-1234-567890abcdef",
						"displayname":"Player2",
						"lastLogin":   1715256869000,
						"lastLogout":  1715261290000,
						"stats": {
							"Bedwars": {
								"Experience": 500
							}
						}
					}
				}`),
			},
			{
				name: "experience only",
				player: &domain.PlayerPIT{
					QueriedAt:  queriedAt,
					UUID:       "12345678-90ab-cdef-1234-567890abcdef",
					Experience: 1087.0,
				},
				result: []byte(`{
					"success": true,
					"player": {
						"uuid":"12345678-90ab-cdef-1234-567890abcdef",
						"stats": {
							"Bedwars": {
								"Experience": 1087
							}
						}
					}
				}`),
			},
			{
				name: "disabled apis",
				player: &domain.PlayerPIT{
					QueriedAt: queriedAt,

					UUID: "12345678-90ab-cdef-1234-567890abcdef",

					Displayname: ptr("disabledapis"),
					LastLogin:   nil,
					LastLogout:  nil,

					MissingBedwarsStats: false,

					Experience: 1_087_000,
					Solo: domain.GamemodeStatsPIT{
						Winstreak:   nil,
						GamesPlayed: 1,
						Wins:        2,
						Losses:      3,
						BedsBroken:  3,
						BedsLost:    4,
						FinalKills:  6,
						FinalDeaths: 7,
						Kills:       8,
						Deaths:      9,
					},
					Doubles: domain.GamemodeStatsPIT{
						Winstreak:   nil,
						GamesPlayed: 101,
						Wins:        102,
						Losses:      103,
						BedsBroken:  104,
						BedsLost:    105,
						FinalKills:  106,
						FinalDeaths: 107,
						Kills:       108,
						Deaths:      109,
					},
					Threes: domain.GamemodeStatsPIT{
						Winstreak:   nil,
						GamesPlayed: 201,
						Wins:        202,
						Losses:      203,
						BedsBroken:  204,
						BedsLost:    205,
						FinalKills:  206,
						FinalDeaths: 207,
						Kills:       208,
						Deaths:      209,
					},
					Fours: domain.GamemodeStatsPIT{
						Winstreak:   nil,
						GamesPlayed: 301,
						Wins:        302,
						Losses:      303,
						BedsBroken:  304,
						BedsLost:    305,
						FinalKills:  306,
						FinalDeaths: 307,
						Kills:       308,
						Deaths:      309,
					},
					Overall: domain.GamemodeStatsPIT{
						Winstreak:   nil,
						GamesPlayed: 401,
						Wins:        402,
						Losses:      403,
						BedsBroken:  404,
						BedsLost:    405,
						FinalKills:  406,
						FinalDeaths: 407,
						Kills:       408,
						Deaths:      409,
					},
				},
				result: []byte(`{
					"success": true,
					"player": {
						"uuid": "12345678-90ab-cdef-1234-567890abcdef",
						"displayname": "disabledapis",
						"stats": {
							"Bedwars": {
								"Experience":                       1087000,
								"eight_one_games_played_bedwars":   1,
								"eight_one_wins_bedwars":           2,
								"eight_one_losses_bedwars":         3,
								"eight_one_beds_broken_bedwars":    3,
								"eight_one_beds_lost_bedwars":      4,
								"eight_one_final_kills_bedwars":    6,
								"eight_one_final_deaths_bedwars":   7,
								"eight_one_kills_bedwars":          8,
								"eight_one_deaths_bedwars":         9,
								"eight_two_games_played_bedwars":   101,
								"eight_two_wins_bedwars":           102,
								"eight_two_losses_bedwars":         103,
								"eight_two_beds_broken_bedwars":    104,
								"eight_two_beds_lost_bedwars":      105,
								"eight_two_final_kills_bedwars":    106,
								"eight_two_final_deaths_bedwars":   107,
								"eight_two_kills_bedwars":          108,
								"eight_two_deaths_bedwars":         109,
								"four_three_games_played_bedwars":  201,
								"four_three_wins_bedwars":          202,
								"four_three_losses_bedwars":        203,
								"four_three_beds_broken_bedwars":   204,
								"four_three_beds_lost_bedwars":     205,
								"four_three_final_kills_bedwars":   206,
								"four_three_final_deaths_bedwars":  207,
								"four_three_kills_bedwars":         208,
								"four_three_deaths_bedwars":        209,
								"four_four_games_played_bedwars":   301,
								"four_four_wins_bedwars":           302,
								"four_four_losses_bedwars":         303,
								"four_four_beds_broken_bedwars":    304,
								"four_four_beds_lost_bedwars":      305,
								"four_four_final_kills_bedwars":    306,
								"four_four_final_deaths_bedwars":   307,
								"four_four_kills_bedwars":          308,
								"four_four_deaths_bedwars":         309,
								"games_played_bedwars":             401,
								"wins_bedwars":                     402,
								"losses_bedwars":                   403,
								"beds_broken_bedwars":              404,
								"beds_lost_bedwars":                405,
								"final_kills_bedwars":              406,
								"final_deaths_bedwars":             407,
								"kills_bedwars":                    408,
								"deaths_bedwars":                   409
							}
						}
					}
				}`),
			},
		}
		for _, c := range cases {
			t.Run(c.name, func(t *testing.T) {
				t.Parallel()
				runPlayerToHypixelAPIResponseTest(t, c)
			})
		}
	})

	t.Run("file cases", func(t *testing.T) {
		t.Parallel()

		hypixelAPIResponseFiles, err := os.ReadDir(hypixelAPIResponsesDir)
		require.NoError(t, err)
		hypixelResponseFileNames := make([]string, 0, len(hypixelAPIResponseFiles))
		for _, file := range hypixelAPIResponseFiles {
			if file.IsDir() {
				continue
			}
			hypixelResponseFileNames = append(hypixelResponseFileNames, file.Name())
		}

		expectedMinifiedDataFiles, err := os.ReadDir(expectedMinifiedDataDir)
		require.NoError(t, err)
		expectedMinifiedDataFileNames := make([]string, 0, len(expectedMinifiedDataFiles))
		for _, file := range expectedMinifiedDataFiles {
			if file.IsDir() {
				continue
			}
			expectedMinifiedDataFileNames = append(expectedMinifiedDataFileNames, file.Name())
		}

		require.ElementsMatch(
			t,
			hypixelResponseFileNames,
			expectedMinifiedDataFileNames,
			"All hypixel api response files must have a corresponding minified data file",
		)

		queriedAt := time.Now()
		for _, name := range hypixelResponseFileNames {
			t.Run(name, func(t *testing.T) {
				t.Parallel()
				hypixelAPIResponse, err := os.ReadFile(path.Join(hypixelAPIResponsesDir, name))
				require.NoError(t, err)
				expectedMinifiedData, err := os.ReadFile(path.Join(expectedMinifiedDataDir, name))
				require.NoError(t, err)

				// Find UUID
				parsedAPIResponse, err := playerprovider.ParseHypixelAPIResponse(context.Background(), hypixelAPIResponse)
				require.NoError(t, err)
				uuid := "12345678-1234-1234-1234-12345678abcd"
				if parsedAPIResponse.Player != nil && parsedAPIResponse.Player.UUID != nil {
					normalizedUUID, err := strutils.NormalizeUUID(*parsedAPIResponse.Player.UUID)
					require.NoError(t, err)
					uuid = normalizedUUID
				}

				player, err := playerprovider.HypixelAPIResponseToPlayerPIT(context.Background(), uuid, queriedAt, hypixelAPIResponse, 200)
				require.NoError(t, err)

				// Real test
				t.Run("real->minified", func(t *testing.T) {
					t.Parallel()
					runPlayerToHypixelAPIResponseTest(t,
						playerToHypixelAPIResponseTestCase{
							name:   name,
							player: player,
							result: expectedMinifiedData,
						},
					)
				})

				// Test that minification is idempotent
				t.Run("minified->minified", func(t *testing.T) {
					t.Parallel()
					playerFromMinified, err := playerprovider.HypixelAPIResponseToPlayerPIT(context.Background(), uuid, queriedAt, hypixelAPIResponse, 200)
					require.NoError(t, err)
					runPlayerToHypixelAPIResponseTest(t,
						playerToHypixelAPIResponseTestCase{
							name:   fmt.Sprintf("%s (minified)", name),
							player: playerFromMinified,
							result: expectedMinifiedData,
						},
					)
				})
			})
		}

	})
}
