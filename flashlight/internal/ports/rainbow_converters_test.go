package ports_test

import (
	"testing"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/ports"
	"github.com/stretchr/testify/require"
)

func TestPlayerToRainbowPlayerPITData(t *testing.T) {
	t.Parallel()

	queriedAt := time.Date(2024, time.February, 24, 14, 17, 59, 123_456_789, time.UTC)

	timePtr := func(timeStr string) *time.Time {
		t.Helper()
		timeTime, err := time.Parse(time.RFC3339, timeStr)
		require.NoError(t, err)
		return &timeTime
	}

	type playerToRainbowPlayerPITTestCase struct {
		name   string
		player *domain.PlayerPIT
		result []byte
		error  bool
	}

	cases := []playerToRainbowPlayerPITTestCase{
		{
			name:   "no player",
			player: nil,
			error:  true,
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
					Winstreak:   ptr(200),
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
				"queriedAt": "2024-02-24T14:17:59.123456789Z",

				"uuid": "12345678-90ab-cdef-1234-567890abcdef",

				"experience": 1087000,
				"solo": {
					"winstreak":    0,
					"gamesPlayed":  1,
					"wins":         2,
					"losses":       3,
					"bedsBroken":   3,
					"bedsLost":     4,
					"finalKills":   6,
					"finalDeaths":  7,
					"kills":        8,
					"deaths":       9
				},
				"doubles": {
					"winstreak":    100,
					"gamesPlayed":  101,
					"wins":         102,
					"losses":       103,
					"bedsBroken":   104,
					"bedsLost":     105,
					"finalKills":   106,
					"finalDeaths":  107,
					"kills":        108,
					"deaths":       109
				},
				"threes": {
					"winstreak":    200,
					"gamesPlayed":  201,
					"wins":         202,
					"losses":       203,
					"bedsBroken":   204,
					"bedsLost":     205,
					"finalKills":   206,
					"finalDeaths":  207,
					"kills":        208,
					"deaths":       209
				},
				"fours": {
					"winstreak":    300,
					"gamesPlayed":  301,
					"wins":         302,
					"losses":       303,
					"bedsBroken":   304,
					"bedsLost":     305,
					"finalKills":   306,
					"finalDeaths":  307,
					"kills":        308,
					"deaths":       309
				},
				"overall": {
					"winstreak":    400,
					"gamesPlayed":  401,
					"wins":         402,
					"losses":       403,
					"bedsBroken":   404,
					"bedsLost":     405,
					"finalKills":   406,
					"finalDeaths":  407,
					"kills":        408,
					"deaths":       409
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
				"queriedAt": "2024-02-24T14:17:59.123456789Z",
				"uuid":"12345678-90ab-cdef-1234-567890abcdef",
				"experience": 500,
				"solo": {
					"winstreak":    null,
					"gamesPlayed":  0,
					"wins":         0,
					"losses":       0,
					"bedsBroken":   0,
					"bedsLost":     0,
					"finalKills":   0,
					"finalDeaths":  0,
					"kills":        0,
					"deaths":       0
				},
				"doubles": {
					"winstreak":    null,
					"gamesPlayed":  0,
					"wins":         0,
					"losses":       0,
					"bedsBroken":   0,
					"bedsLost":     0,
					"finalKills":   0,
					"finalDeaths":  0,
					"kills":        0,
					"deaths":       0
				},
				"threes": {
					"winstreak":    null,
					"gamesPlayed":  0,
					"wins":         0,
					"losses":       0,
					"bedsBroken":   0,
					"bedsLost":     0,
					"finalKills":   0,
					"finalDeaths":  0,
					"kills":        0,
					"deaths":       0
				},
				"fours": {
					"winstreak":    null,
					"gamesPlayed":  0,
					"wins":         0,
					"losses":       0,
					"bedsBroken":   0,
					"bedsLost":     0,
					"finalKills":   0,
					"finalDeaths":  0,
					"kills":        0,
					"deaths":       0
				},
				"overall": {
					"winstreak":    null,
					"gamesPlayed":  0,
					"wins":         0,
					"losses":       0,
					"bedsBroken":   0,
					"bedsLost":     0,
					"finalKills":   0,
					"finalDeaths":  0,
					"kills":        0,
					"deaths":       0
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
				"queriedAt": "2024-02-24T14:17:59.123456789Z",
				"uuid":"12345678-90ab-cdef-1234-567890abcdef",
				"experience": 1087,
				"solo": {
					"winstreak":    null,
					"gamesPlayed":  0,
					"wins":         0,
					"losses":       0,
					"bedsBroken":   0,
					"bedsLost":     0,
					"finalKills":   0,
					"finalDeaths":  0,
					"kills":        0,
					"deaths":       0
				},
				"doubles": {
					"winstreak":    null,
					"gamesPlayed":  0,
					"wins":         0,
					"losses":       0,
					"bedsBroken":   0,
					"bedsLost":     0,
					"finalKills":   0,
					"finalDeaths":  0,
					"kills":        0,
					"deaths":       0
				},
				"threes": {
					"winstreak":    null,
					"gamesPlayed":  0,
					"wins":         0,
					"losses":       0,
					"bedsBroken":   0,
					"bedsLost":     0,
					"finalKills":   0,
					"finalDeaths":  0,
					"kills":        0,
					"deaths":       0
				},
				"fours": {
					"winstreak":    null,
					"gamesPlayed":  0,
					"wins":         0,
					"losses":       0,
					"bedsBroken":   0,
					"bedsLost":     0,
					"finalKills":   0,
					"finalDeaths":  0,
					"kills":        0,
					"deaths":       0
				},
				"overall": {
					"winstreak":    null,
					"gamesPlayed":  0,
					"wins":         0,
					"losses":       0,
					"bedsBroken":   0,
					"bedsLost":     0,
					"finalKills":   0,
					"finalDeaths":  0,
					"kills":        0,
					"deaths":       0
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
				"queriedAt": "2024-02-24T14:17:59.123456789Z",

				"uuid": "12345678-90ab-cdef-1234-567890abcdef",

				"experience": 1087000,
				"solo": {
					"winstreak":    null,
					"gamesPlayed":  1,
					"wins":         2,
					"losses":       3,
					"bedsBroken":   3,
					"bedsLost":     4,
					"finalKills":   6,
					"finalDeaths":  7,
					"kills":        8,
					"deaths":       9
				},
				"doubles": {
					"winstreak":    null,
					"gamesPlayed":  101,
					"wins":         102,
					"losses":       103,
					"bedsBroken":   104,
					"bedsLost":     105,
					"finalKills":   106,
					"finalDeaths":  107,
					"kills":        108,
					"deaths":       109
				},
				"threes": {
					"winstreak":    null,
					"gamesPlayed":  201,
					"wins":         202,
					"losses":       203,
					"bedsBroken":   204,
					"bedsLost":     205,
					"finalKills":   206,
					"finalDeaths":  207,
					"kills":        208,
					"deaths":       209
				},
				"fours": {
					"winstreak":    null,
					"gamesPlayed":  301,
					"wins":         302,
					"losses":       303,
					"bedsBroken":   304,
					"bedsLost":     305,
					"finalKills":   306,
					"finalDeaths":  307,
					"kills":        308,
					"deaths":       309
				},
				"overall": {
					"winstreak":    null,
					"gamesPlayed":  401,
					"wins":         402,
					"losses":       403,
					"bedsBroken":   404,
					"bedsLost":     405,
					"finalKills":   406,
					"finalDeaths":  407,
					"kills":        408,
					"deaths":       409
				}
			}`),
		},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			t.Parallel()

			data, err := ports.PlayerToRainbowPlayerDataPITData(c.player)
			if c.error {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)

			require.JSONEq(t, string(c.result), string(data))
		})
	}
}

func TestHistoryToRainbowHistoryData(t *testing.T) {
	t.Parallel()

	queriedAt := time.Date(2024, time.February, 24, 14, 17, 59, 123_456_789, time.UTC)

	timePtr := func(timeStr string) *time.Time {
		t.Helper()
		timeTime, err := time.Parse(time.RFC3339, timeStr)
		require.NoError(t, err)
		return &timeTime
	}

	type playerToRainbowPlayerPITTestCase struct {
		name    string
		history []domain.PlayerPIT
		result  []byte
		error   bool
	}

	cases := []playerToRainbowPlayerPITTestCase{
		{
			name:    "nil history",
			history: nil,
			result:  []byte(`[]`),
		},
		{
			name:    "empty history",
			history: []domain.PlayerPIT{},
			result:  []byte(`[]`),
		},
		{
			name: "non-empty history",
			history: []domain.PlayerPIT{
				{
					QueriedAt: queriedAt,

					UUID: "12345678-90ab-cdef-1234-567890abcdef",

					Displayname: ptr("disabledapis"),
					LastLogin:   timePtr("2023-01-01T00:00:00Z"),
					LastLogout:  nil,

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
				{
					QueriedAt:  queriedAt.Add(1 * time.Hour),
					UUID:       "12345678-90ab-cdef-1234-567890abcdef",
					Experience: 1087.0,
				},
			},

			result: []byte(`[
				{
					"queriedAt": "2024-02-24T14:17:59.123456789Z",

					"uuid": "12345678-90ab-cdef-1234-567890abcdef",

					"experience": 1087000,
					"solo": {
						"winstreak":    0,
						"gamesPlayed":  1,
						"wins":         2,
						"losses":       3,
						"bedsBroken":   3,
						"bedsLost":     4,
						"finalKills":   6,
						"finalDeaths":  7,
						"kills":        8,
						"deaths":       9
					},
					"doubles": {
						"winstreak":    100,
						"gamesPlayed":  101,
						"wins":         102,
						"losses":       103,
						"bedsBroken":   104,
						"bedsLost":     105,
						"finalKills":   106,
						"finalDeaths":  107,
						"kills":        108,
						"deaths":       109
					},
					"threes": {
						"winstreak":    null,
						"gamesPlayed":  201,
						"wins":         202,
						"losses":       203,
						"bedsBroken":   204,
						"bedsLost":     205,
						"finalKills":   206,
						"finalDeaths":  207,
						"kills":        208,
						"deaths":       209
					},
					"fours": {
						"winstreak":    null,
						"gamesPlayed":  301,
						"wins":         302,
						"losses":       303,
						"bedsBroken":   304,
						"bedsLost":     305,
						"finalKills":   306,
						"finalDeaths":  307,
						"kills":        308,
						"deaths":       309
					},
					"overall": {
						"winstreak":    null,
						"gamesPlayed":  401,
						"wins":         402,
						"losses":       403,
						"bedsBroken":   404,
						"bedsLost":     405,
						"finalKills":   406,
						"finalDeaths":  407,
						"kills":        408,
						"deaths":       409
					}
				},
				{
					"queriedAt": "2024-02-24T15:17:59.123456789Z",
					"uuid":"12345678-90ab-cdef-1234-567890abcdef",
					"experience": 1087,
					"solo": {
						"winstreak":    null,
						"gamesPlayed":  0,
						"wins":         0,
						"losses":       0,
						"bedsBroken":   0,
						"bedsLost":     0,
						"finalKills":   0,
						"finalDeaths":  0,
						"kills":        0,
						"deaths":       0
					},
					"doubles": {
						"winstreak":    null,
						"gamesPlayed":  0,
						"wins":         0,
						"losses":       0,
						"bedsBroken":   0,
						"bedsLost":     0,
						"finalKills":   0,
						"finalDeaths":  0,
						"kills":        0,
						"deaths":       0
					},
					"threes": {
						"winstreak":    null,
						"gamesPlayed":  0,
						"wins":         0,
						"losses":       0,
						"bedsBroken":   0,
						"bedsLost":     0,
						"finalKills":   0,
						"finalDeaths":  0,
						"kills":        0,
						"deaths":       0
					},
					"fours": {
						"winstreak":    null,
						"gamesPlayed":  0,
						"wins":         0,
						"losses":       0,
						"bedsBroken":   0,
						"bedsLost":     0,
						"finalKills":   0,
						"finalDeaths":  0,
						"kills":        0,
						"deaths":       0
					},
					"overall": {
						"winstreak":    null,
						"gamesPlayed":  0,
						"wins":         0,
						"losses":       0,
						"bedsBroken":   0,
						"bedsLost":     0,
						"finalKills":   0,
						"finalDeaths":  0,
						"kills":        0,
						"deaths":       0
					}
				}
			]`),
		},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			t.Parallel()

			data, err := ports.HistoryToRainbowHistoryData(c.history)
			if c.error {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)

			require.JSONEq(t, string(c.result), string(data))
		})
	}
}

func TestSessionsToRainbowSessionsData(t *testing.T) {
	t.Parallel()

	queriedAt := time.Date(2024, time.February, 24, 14, 17, 59, 123_456_789, time.UTC)

	timePtr := func(timeStr string) *time.Time {
		t.Helper()
		timeTime, err := time.Parse(time.RFC3339, timeStr)
		require.NoError(t, err)
		return &timeTime
	}

	type playerToRainbowPlayerPITTestCase struct {
		name     string
		sessions []domain.Session
		result   []byte
		error    bool
	}

	cases := []playerToRainbowPlayerPITTestCase{
		{
			name:     "nil sessions",
			sessions: nil,
			result:   []byte(`[]`),
		},
		{
			name:     "empty sessions",
			sessions: []domain.Session{},
			result:   []byte(`[]`),
		},
		{
			name: "non-empty sessions",
			sessions: []domain.Session{
				{
					Start: domain.PlayerPIT{
						QueriedAt: queriedAt,

						UUID: "12345678-90ab-cdef-1234-567890abcdef",

						Displayname: ptr("disabledapis"),
						LastLogin:   timePtr("2023-01-01T00:00:00Z"),
						LastLogout:  nil,

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
					End: domain.PlayerPIT{
						QueriedAt:  queriedAt,
						UUID:       "12345678-90ab-cdef-1234-567890abcdef",
						Experience: 1087.0,
					},
					Consecutive: true,
				},
			},

			result: []byte(`[
			{
				"start": {
					"queriedAt": "2024-02-24T14:17:59.123456789Z",

					"uuid": "12345678-90ab-cdef-1234-567890abcdef",

					"experience": 1087000,
					"solo": {
						"winstreak":    0,
						"gamesPlayed":  1,
						"wins":         2,
						"losses":       3,
						"bedsBroken":   3,
						"bedsLost":     4,
						"finalKills":   6,
						"finalDeaths":  7,
						"kills":        8,
						"deaths":       9
					},
					"doubles": {
						"winstreak":    100,
						"gamesPlayed":  101,
						"wins":         102,
						"losses":       103,
						"bedsBroken":   104,
						"bedsLost":     105,
						"finalKills":   106,
						"finalDeaths":  107,
						"kills":        108,
						"deaths":       109
					},
					"threes": {
						"winstreak":    null,
						"gamesPlayed":  201,
						"wins":         202,
						"losses":       203,
						"bedsBroken":   204,
						"bedsLost":     205,
						"finalKills":   206,
						"finalDeaths":  207,
						"kills":        208,
						"deaths":       209
					},
					"fours": {
						"winstreak":    null,
						"gamesPlayed":  301,
						"wins":         302,
						"losses":       303,
						"bedsBroken":   304,
						"bedsLost":     305,
						"finalKills":   306,
						"finalDeaths":  307,
						"kills":        308,
						"deaths":       309
					},
					"overall": {
						"winstreak":    null,
						"gamesPlayed":  401,
						"wins":         402,
						"losses":       403,
						"bedsBroken":   404,
						"bedsLost":     405,
						"finalKills":   406,
						"finalDeaths":  407,
						"kills":        408,
						"deaths":       409
					}
				},
				"end": {
					"queriedAt": "2024-02-24T14:17:59.123456789Z",
					"uuid":"12345678-90ab-cdef-1234-567890abcdef",
					"experience": 1087,
					"solo": {
						"winstreak":    null,
						"gamesPlayed":  0,
						"wins":         0,
						"losses":       0,
						"bedsBroken":   0,
						"bedsLost":     0,
						"finalKills":   0,
						"finalDeaths":  0,
						"kills":        0,
						"deaths":       0
					},
					"doubles": {
						"winstreak":    null,
						"gamesPlayed":  0,
						"wins":         0,
						"losses":       0,
						"bedsBroken":   0,
						"bedsLost":     0,
						"finalKills":   0,
						"finalDeaths":  0,
						"kills":        0,
						"deaths":       0
					},
					"threes": {
						"winstreak":    null,
						"gamesPlayed":  0,
						"wins":         0,
						"losses":       0,
						"bedsBroken":   0,
						"bedsLost":     0,
						"finalKills":   0,
						"finalDeaths":  0,
						"kills":        0,
						"deaths":       0
					},
					"fours": {
						"winstreak":    null,
						"gamesPlayed":  0,
						"wins":         0,
						"losses":       0,
						"bedsBroken":   0,
						"bedsLost":     0,
						"finalKills":   0,
						"finalDeaths":  0,
						"kills":        0,
						"deaths":       0
					},
					"overall": {
						"winstreak":    null,
						"gamesPlayed":  0,
						"wins":         0,
						"losses":       0,
						"bedsBroken":   0,
						"bedsLost":     0,
						"finalKills":   0,
						"finalDeaths":  0,
						"kills":        0,
						"deaths":       0
					}
				},
				"consecutive": true
			}
			]`),
		},
	}

	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			t.Parallel()

			data, err := ports.SessionsToRainbowSessionsData(c.sessions)
			if c.error {
				require.Error(t, err)
				return
			}
			require.NoError(t, err)

			require.JSONEq(t, string(c.result), string(data))
		})
	}
}
