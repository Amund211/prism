package ports

import (
	"context"
	"testing"
	"time"

	"github.com/Amund211/flashlight/internal/domain"
	"github.com/Amund211/flashlight/internal/domaintest"
	"github.com/stretchr/testify/require"
)

func TestComputeSessionLengths(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	playerUUID := domaintest.NewUUID(t)

	tests := []struct {
		name     string
		sessions []domain.Session
		want     sessionLengthStats
	}{
		{
			name: "single session",
			sessions: []domain.Session{
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 10, 0, 0, 0, time.UTC)).Build(),
					End:   domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 12, 0, 0, 0, time.UTC)).Build(),
				},
			},
			want: sessionLengthStats{
				TotalHours:    2.0,
				LongestHours:  2.0,
				ShortestHours: 2.0,
				AverageHours:  2.0,
			},
		},
		{
			name: "multiple sessions",
			sessions: []domain.Session{
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 10, 0, 0, 0, time.UTC)).Build(),
					End:   domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 12, 0, 0, 0, time.UTC)).Build(),
				},
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 2, 14, 0, 0, 0, time.UTC)).Build(),
					End:   domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 2, 18, 0, 0, 0, time.UTC)).Build(),
				},
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 3, 9, 0, 0, 0, time.UTC)).Build(),
					End:   domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 3, 10, 0, 0, 0, time.UTC)).Build(),
				},
			},
			want: sessionLengthStats{
				TotalHours:    7.0,
				LongestHours:  4.0,
				ShortestHours: 1.0,
				AverageHours:  (2.0 + 4.0 + 1.0) / 3.0,
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			got := computeSessionLengths(ctx, tt.sessions)
			require.Equal(t, tt.want, got)
		})
	}
}

func TestComputeSessionsPerMonth(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	playerUUID := domaintest.NewUUID(t)

	tests := []struct {
		name     string
		year     int
		sessions []domain.Session
		want     sessionsPerMonth
	}{
		{
			name: "sessions in different months",
			year: 2023,
			sessions: []domain.Session{
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2022, time.December, 31, 10, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(0).Build()).Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 11, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(1).Build()).Build(),
				},
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 15, 10, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(0).Build()).Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 15, 11, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(1).Build()).Build(),
				},
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 20, 10, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(1).Build()).Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 20, 11, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(2).Build()).Build(),
				},
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.March, 10, 10, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(2).Build()).Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.March, 10, 11, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(3).Build()).Build(),
				},
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.December, 25, 10, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(3).Build()).Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.December, 25, 11, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(4).Build()).Build(),
				},
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.December, 31, 10, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(0).Build()).Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2024, time.January, 1, 11, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(1).Build()).Build(),
				},
			},
			want: sessionsPerMonth{
				time.January:  3,
				time.March:    1,
				time.December: 2,
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			got := computeSessionsPerMonth(ctx, tt.sessions, tt.year)
			require.Equal(t, tt.want, got)
		})
	}
}

func TestComputeFlawlessSessions(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	playerUUID := domaintest.NewUUID(t)
	start := time.Date(2023, time.January, 1, 10, 0, 0, 0, time.UTC)

	tests := []struct {
		name     string
		sessions []domain.Session
		want     flawlessSessionStats
	}{
		{
			name: "no flawless sessions - has losses or final deaths",
			sessions: []domain.Session{
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, start).
						WithOverallStats(domaintest.NewStatsBuilder().WithLosses(0).WithFinalDeaths(0).Build()).Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, start.Add(time.Hour)).
						WithOverallStats(domaintest.NewStatsBuilder().WithLosses(1).WithFinalDeaths(0).Build()).Build(),
				},
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour)).
						WithOverallStats(domaintest.NewStatsBuilder().WithLosses(1).WithFinalDeaths(0).Build()).Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour)).
						WithOverallStats(domaintest.NewStatsBuilder().WithLosses(1).WithFinalDeaths(1).Build()).Build(),
				},
			},
			want: flawlessSessionStats{
				Count:      0,
				Percentage: 0,
			},
		},
		{
			name: "all flawless sessions",
			sessions: []domain.Session{
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, start).
						WithOverallStats(domaintest.NewStatsBuilder().WithLosses(0).WithFinalDeaths(0).WithWins(0).Build()).Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, start.Add(time.Hour)).
						WithOverallStats(domaintest.NewStatsBuilder().WithLosses(0).WithFinalDeaths(0).WithWins(5).Build()).Build(),
				},
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour)).
						WithOverallStats(domaintest.NewStatsBuilder().WithLosses(0).WithFinalDeaths(0).WithWins(5).Build()).Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour)).
						WithOverallStats(domaintest.NewStatsBuilder().WithLosses(0).WithFinalDeaths(0).WithWins(10).Build()).Build(),
				},
			},
			want: flawlessSessionStats{
				Count:      2,
				Percentage: 100,
			},
		},
		{
			name: "mixed sessions - 2 flawless out of 4",
			sessions: []domain.Session{
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, start).
						WithOverallStats(domaintest.NewStatsBuilder().WithLosses(0).WithFinalDeaths(0).WithWins(0).Build()).Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, start.Add(time.Hour)).
						WithOverallStats(domaintest.NewStatsBuilder().WithLosses(0).WithFinalDeaths(0).WithWins(2).Build()).Build(),
				},
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, start.Add(2*time.Hour)).
						WithOverallStats(domaintest.NewStatsBuilder().WithLosses(0).WithFinalDeaths(0).WithWins(2).Build()).Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, start.Add(3*time.Hour)).
						WithOverallStats(domaintest.NewStatsBuilder().WithLosses(1).WithFinalDeaths(0).WithWins(2).Build()).Build(),
				},
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, start.Add(4*time.Hour)).
						WithOverallStats(domaintest.NewStatsBuilder().WithLosses(1).WithFinalDeaths(0).WithWins(2).Build()).Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, start.Add(5*time.Hour)).
						WithOverallStats(domaintest.NewStatsBuilder().WithLosses(1).WithFinalDeaths(0).WithWins(5).Build()).Build(),
				},
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, start.Add(6*time.Hour)).
						WithOverallStats(domaintest.NewStatsBuilder().WithLosses(1).WithFinalDeaths(0).WithWins(5).Build()).Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, start.Add(7*time.Hour)).
						WithOverallStats(domaintest.NewStatsBuilder().WithLosses(1).WithFinalDeaths(1).WithWins(5).Build()).Build(),
				},
			},
			want: flawlessSessionStats{
				Count:      2,
				Percentage: 50,
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			require.Equal(t, tt.want, computeFlawlessSessions(ctx, tt.sessions))
		})
	}
}

func TestComputeAverages(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	playerUUID := domaintest.NewUUID(t)

	tests := []struct {
		name     string
		sessions []domain.Session
		want     *averageStats
	}{
		{
			name: "single session",
			sessions: []domain.Session{
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 10, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(0).WithWins(0).WithFinalKills(0).Build()).Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 12, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(10).WithWins(5).WithFinalKills(20).Build()).Build(),
				},
			},
			want: &averageStats{
				SessionLength: 2.0,
				GamesPlayed:   10.0,
				Wins:          5.0,
				FinalKills:    20.0,
			},
		},
		{
			name: "multiple sessions",
			sessions: []domain.Session{
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 10, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(0).WithWins(0).WithFinalKills(0).Build()).Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 12, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(10).WithWins(5).WithFinalKills(20).Build()).Build(),
				},
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 2, 14, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(10).WithWins(5).WithFinalKills(20).Build()).Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 2, 18, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(30).WithWins(15).WithFinalKills(60).Build()).Build(),
				},
			},
			want: &averageStats{
				SessionLength: (2.0 + 4.0) / 2,
				GamesPlayed:   (10.0 + 20.0) / 2,
				Wins:          (5.0 + 10.0) / 2,
				FinalKills:    (20.0 + 40.0) / 2,
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			got := computeAverages(ctx, tt.sessions)
			if tt.want == nil {
				require.Nil(t, got)
			} else {
				require.NotNil(t, got)
				require.InDelta(t, tt.want.SessionLength, got.SessionLength, 0.0001)
				require.InDelta(t, tt.want.GamesPlayed, got.GamesPlayed, 0.0001)
				require.InDelta(t, tt.want.Wins, got.Wins, 0.0001)
				require.InDelta(t, tt.want.FinalKills, got.FinalKills, 0.0001)
			}
		})
	}
}

func TestComputeYearBoundaryStats(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	playerUUID := domaintest.NewUUID(t)

	tests := []struct {
		name       string
		playerPITs []domain.PlayerPIT
		year       int
		wantStart  *time.Time
		wantEnd    *time.Time
	}{
		{
			name: "single PIT in year",
			playerPITs: []domain.PlayerPIT{
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.June, 15, 12, 0, 0, 0, time.UTC)).Build(),
			},
			year:      2023,
			wantStart: timePtr(time.Date(2023, time.June, 15, 12, 0, 0, 0, time.UTC)),
			wantEnd:   timePtr(time.Date(2023, time.June, 15, 12, 0, 0, 0, time.UTC)),
		},
		{
			name: "multiple PITs in year",
			playerPITs: []domain.PlayerPIT{
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 0, 0, 0, 0, time.UTC)).Build(),
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.June, 15, 12, 0, 0, 0, time.UTC)).Build(),
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.December, 31, 23, 59, 59, 0, time.UTC)).Build(),
			},
			year:      2023,
			wantStart: timePtr(time.Date(2023, time.January, 1, 0, 0, 0, 0, time.UTC)),
			wantEnd:   timePtr(time.Date(2023, time.December, 31, 23, 59, 59, 0, time.UTC)),
		},
		{
			name: "PITs outside year",
			playerPITs: []domain.PlayerPIT{
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2022, time.December, 31, 23, 59, 59, 0, time.UTC)).Build(),
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2024, time.January, 1, 0, 0, 0, 0, time.UTC)).Build(),
			},
			year:      2023,
			wantStart: nil,
			wantEnd:   nil,
		},
		{
			name: "weird order - unrealistic",
			playerPITs: []domain.PlayerPIT{
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.June, 15, 12, 0, 0, 0, time.UTC)).Build(),
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.December, 31, 23, 59, 59, 0, time.UTC)).Build(),
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 0, 0, 0, 0, time.UTC)).Build(),
			},
			year:      2023,
			wantStart: timePtr(time.Date(2023, time.January, 1, 0, 0, 0, 0, time.UTC)),
			wantEnd:   timePtr(time.Date(2023, time.December, 31, 23, 59, 59, 0, time.UTC)),
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			got := computeYearBoundaryStats(ctx, tt.playerPITs, tt.year)
			if tt.wantStart == nil && tt.wantEnd == nil {
				require.Nil(t, got)
				return
			}

			require.NotNil(t, got)
			require.Equal(t, *tt.wantStart, got.Start.QueriedAt)
			require.Equal(t, *tt.wantEnd, got.End.QueriedAt)
		})
	}
}

func TestComputeCoverage(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	playerUUID := domaintest.NewUUID(t)

	tests := []struct {
		name                   string
		sessions               []domain.Session
		boundaryStats          *yearBoundaryStats
		totalHours             float64
		wantCoverage           float64
		wantAdjustedTotalHours float64
	}{
		{
			name: "100% coverage",
			boundaryStats: &yearBoundaryStats{
				Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 0, 0, 0, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(0).Build()).BuildPtr(),
				End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.December, 31, 23, 59, 59, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(100).Build()).BuildPtr(),
			},
			sessions: []domain.Session{
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.June, 1, 10, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(0).Build()).Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.June, 1, 12, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(100).Build()).Build(),
				},
			},
			totalHours:             2.0,
			wantCoverage:           100.0,
			wantAdjustedTotalHours: 2.0,
		},
		{
			name: "50% coverage",
			boundaryStats: &yearBoundaryStats{
				Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 0, 0, 0, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(0).Build()).BuildPtr(),
				End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.December, 31, 23, 59, 59, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(100).Build()).BuildPtr(),
			},
			sessions: []domain.Session{
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.June, 1, 10, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(0).Build()).Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.June, 1, 12, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(50).Build()).Build(),
				},
			},
			totalHours:             2.0,
			wantCoverage:           50.0,
			wantAdjustedTotalHours: 4.0,
		},
		{
			name: "0% coverage",
			boundaryStats: &yearBoundaryStats{
				Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 0, 0, 0, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(0).Build()).BuildPtr(),
				End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.December, 31, 23, 59, 59, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(100).Build()).BuildPtr(),
			},
			sessions: []domain.Session{
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.June, 1, 10, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(0).Build()).Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.June, 1, 12, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(0).Build()).Build(),
				},
			},
			totalHours:             2.0,
			wantCoverage:           0.0,
			wantAdjustedTotalHours: 2.0,
		},
		{
			name: "coverage over 100%",
			boundaryStats: &yearBoundaryStats{
				Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 0, 0, 0, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(0).Build()).BuildPtr(),
				End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.December, 31, 23, 59, 59, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(50).Build()).BuildPtr(),
			},
			sessions: []domain.Session{
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.June, 1, 10, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(0).Build()).Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.June, 1, 12, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(100).Build()).Build(),
				},
			},
			totalHours:             2.0,
			wantCoverage:           100.0,
			wantAdjustedTotalHours: 2.0, // Should keep sessionDuration when > 100%
		},
		{
			name:          "missing boundary stats",
			boundaryStats: nil,
			sessions: []domain.Session{
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.June, 1, 10, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(0).Build()).Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.June, 1, 12, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(100).Build()).Build(),
				},
			},
			totalHours:             2.0,
			wantCoverage:           0,
			wantAdjustedTotalHours: 2.0,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			got := computeCoverage(ctx, tt.sessions, tt.boundaryStats, tt.totalHours)
			require.Equal(t, tt.wantCoverage, got.GamesPlayedPercentage)
			require.Equal(t, got.AdjustedTotalHours, tt.wantAdjustedTotalHours)
		})
	}
}

func TestComputeBestSessions(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	playerUUID := domaintest.NewUUID(t)

	tests := []struct {
		name              string
		sessions          []domain.Session
		wantHighestFKDR   float64
		wantMostKills     int
		wantMostFinals    int
		wantMostWins      int
		wantLongestHours  float64
		wantWinsPerHour   *float64
		wantFinalsPerHour *float64
	}{
		{
			name: "single session",
			sessions: []domain.Session{
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 10, 0, 0, 0, time.UTC)).
						FromDB().
						WithOverallStats(domaintest.NewStatsBuilder().
							WithKills(0).WithFinalKills(0).WithWins(0).WithFinalDeaths(0).Build()).Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 12, 0, 0, 0, time.UTC)).
						FromDB().
						WithOverallStats(domaintest.NewStatsBuilder().
							WithKills(50).WithFinalKills(20).WithWins(5).WithFinalDeaths(2).Build()).Build(),
				},
			},
			wantHighestFKDR:   20.0 / 2.0,
			wantMostKills:     50,
			wantMostFinals:    20,
			wantMostWins:      5,
			wantLongestHours:  2.0,
			wantWinsPerHour:   float64Ptr(5.0 / 2.0),
			wantFinalsPerHour: float64Ptr(20.0 / 2.0),
		},
		{
			name: "FKDR with zero final deaths - should use final kills as FKDR",
			sessions: []domain.Session{
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 10, 0, 0, 0, time.UTC)).
						FromDB().
						WithOverallStats(domaintest.NewStatsBuilder().
							WithKills(0).WithFinalKills(0).WithWins(0).WithFinalDeaths(0).Build()).Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 12, 0, 0, 0, time.UTC)).
						FromDB().
						WithOverallStats(domaintest.NewStatsBuilder().
							WithKills(50).WithFinalKills(15).WithWins(5).WithFinalDeaths(0).Build()).Build(),
				},
			},
			wantHighestFKDR:   15.0, // 15 final kills with 0 deaths
			wantMostKills:     50,
			wantMostFinals:    15,
			wantMostWins:      5,
			wantLongestHours:  2.0,
			wantWinsPerHour:   float64Ptr(5.0 / 2.0),
			wantFinalsPerHour: float64Ptr(15.0 / 2.0),
		},
		{
			name: "multiple sessions with different bests",
			sessions: []domain.Session{
				// Session 1: 1 hour, FKDR=10 (10/1), 100 kills, 10 finals, 2 wins
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 10, 0, 0, 0, time.UTC)).
						FromDB().
						WithOverallStats(domaintest.NewStatsBuilder().
							WithKills(0).WithFinalKills(0).WithWins(0).WithFinalDeaths(0).Build()).Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 11, 0, 0, 0, time.UTC)).
						FromDB().
						WithOverallStats(domaintest.NewStatsBuilder().
							WithKills(100).WithFinalKills(10).WithWins(2).WithFinalDeaths(1).Build()).Build(),
				},
				// Session 2: 8 hours (longest), FKDR=40 (40/1, highest), 50 kills, 40 finals (most), 20 wins (most)
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 2, 10, 0, 0, 0, time.UTC)).
						FromDB().
						WithOverallStats(domaintest.NewStatsBuilder().
							WithKills(100).WithFinalKills(10).WithWins(2).WithFinalDeaths(1).Build()).Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 2, 18, 0, 0, 0, time.UTC)).
						FromDB().
						WithOverallStats(domaintest.NewStatsBuilder().
							WithKills(150).WithFinalKills(50).WithWins(22).WithFinalDeaths(2).Build()).Build(),
				},
			},
			wantHighestFKDR:   40.0,             // Session 2: 40/1
			wantMostKills:     100,              // Session 1: 100 kills
			wantMostFinals:    40,               // Session 2: 40 finals
			wantMostWins:      20,               // Session 2: 20 wins
			wantLongestHours:  8.0,              // Session 2: 8 hours
			wantWinsPerHour:   float64Ptr(2.5),  // Session 2: 20/8 = 2.5
			wantFinalsPerHour: float64Ptr(10.0), // Session 1: 10/1 = 10.0
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			got := computeBestSessions(ctx, tt.sessions)

			{
				finals := got.HighestFKDR.End.Overall.FinalKills - got.HighestFKDR.Start.Overall.FinalKills
				finalDeaths := got.HighestFKDR.End.Overall.FinalDeaths - got.HighestFKDR.Start.Overall.FinalDeaths
				fkdr := float64(finals)
				if finalDeaths != 0 {
					fkdr = float64(finals) / float64(finalDeaths)
				}
				require.Equal(t, tt.wantHighestFKDR, fkdr)
			}
			require.Equal(t, tt.wantMostKills, got.MostKills.End.Overall.Kills-got.MostKills.Start.Overall.Kills)
			require.Equal(t, tt.wantMostFinals, got.MostFinalKills.End.Overall.FinalKills-got.MostFinalKills.Start.Overall.FinalKills)
			require.Equal(t, tt.wantMostWins, got.MostWins.End.Overall.Wins-got.MostWins.Start.Overall.Wins)
			require.Equal(t, tt.wantLongestHours, got.LongestSession.End.QueriedAt.Sub(got.LongestSession.Start.QueriedAt).Hours())
			if tt.wantWinsPerHour == nil {
				require.Nil(t, got.MostWinsPerHour)
			} else {
				wins := got.MostWins.End.Overall.Wins - got.MostWins.Start.Overall.Wins
				hours := got.MostWins.End.QueriedAt.Sub(got.MostWins.Start.QueriedAt).Hours()
				require.Equal(t, *tt.wantWinsPerHour, float64(wins)/hours)
			}
			if tt.wantFinalsPerHour == nil {
				require.Nil(t, got.MostFinalsPerHour)
			} else {
				finals := got.MostFinalsPerHour.End.Overall.FinalKills - got.MostFinalsPerHour.Start.Overall.FinalKills
				hours := got.MostFinalsPerHour.End.QueriedAt.Sub(got.MostFinalsPerHour.Start.QueriedAt).Hours()
				require.Equal(t, *tt.wantFinalsPerHour, float64(finals)/hours)
			}
		})
	}
}

func TestComputeWinstreaks(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	playerUUID := domaintest.NewUUID(t)

	tests := []struct {
		name            string
		playerPITs      []domain.PlayerPIT
		wantOverallHigh int
	}{
		{
			name: "winstreak of 5 then loss",
			playerPITs: []domain.PlayerPIT{
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 10, 0, 0, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithWins(100).WithLosses(0).Build()).Build(),
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 11, 0, 0, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithWins(105).WithLosses(0).Build()).Build(),
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 12, 0, 0, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithWins(105).WithLosses(1).Build()).Build(),
			},
			wantOverallHigh: 5,
		},
		{
			name: "ongoing winstreak excluded",
			playerPITs: []domain.PlayerPIT{
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 10, 0, 0, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithWins(0).WithLosses(0).Build()).Build(),
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 11, 0, 0, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithWins(6).WithLosses(0).Build()).Build(),
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 12, 0, 0, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithWins(6).WithLosses(1).Build()).Build(),
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.February, 1, 10, 0, 0, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithWins(6).WithLosses(0).Build()).Build(),
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.February, 1, 11, 0, 0, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithWins(100).WithLosses(0).Build()).Build(),
			},
			wantOverallHigh: 6,
		},
		{
			name: "concurrent wins and losses - extra wins don't count",
			playerPITs: []domain.PlayerPIT{
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 10, 0, 0, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithWins(0).WithLosses(0).Build()).Build(),
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 11, 0, 0, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithWins(5).WithLosses(0).Build()).Build(),
				// Both wins and losses increased - we don't know the order
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 12, 0, 0, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithWins(8).WithLosses(1).Build()).Build(),
			},
			wantOverallHigh: 5, // The extra 3 wins don't count toward the streak
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			got := computeWinstreaks(ctx, tt.playerPITs)

			if len(tt.playerPITs) == 0 {
				require.Nil(t, got)
				return
			}
			require.NotNil(t, got)
			require.NotNil(t, got.Overall)

			require.Equal(t, tt.wantOverallHigh, got.Overall.Highest)
		})
	}
}

func TestComputeFinalKillStreaks(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	playerUUID := domaintest.NewUUID(t)

	tests := []struct {
		name            string
		playerPITs      []domain.PlayerPIT
		wantOverallHigh int
	}{
		{
			name: "final kill streak of 8 then death",
			playerPITs: []domain.PlayerPIT{
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 10, 0, 0, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithFinalKills(100).WithFinalDeaths(0).Build()).Build(),
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 11, 0, 0, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithFinalKills(108).WithFinalDeaths(0).Build()).Build(),
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 12, 0, 0, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithFinalKills(108).WithFinalDeaths(1).Build()).Build(),
			},
			wantOverallHigh: 8,
		},
		{
			name: "ongoing streak excluded",
			playerPITs: []domain.PlayerPIT{
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 10, 0, 0, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithFinalKills(0).WithFinalDeaths(0).Build()).Build(),
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 11, 0, 0, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithFinalKills(9).WithFinalDeaths(0).Build()).Build(),
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 12, 0, 0, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithFinalKills(9).WithFinalDeaths(1).Build()).Build(),
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.February, 1, 10, 0, 0, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithFinalKills(9).WithFinalDeaths(0).Build()).Build(),
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.February, 1, 11, 0, 0, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithFinalKills(100).WithFinalDeaths(0).Build()).Build(),
			},
			wantOverallHigh: 9,
		},
		{
			name: "concurrent final kills and deaths - extra kills don't count",
			playerPITs: []domain.PlayerPIT{
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 10, 0, 0, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithFinalKills(0).WithFinalDeaths(0).Build()).Build(),
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 11, 0, 0, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithFinalKills(8).WithFinalDeaths(0).Build()).Build(),
				// Both final kills and deaths increased - we don't know the order
				domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 12, 0, 0, 0, time.UTC)).
					WithOverallStats(domaintest.NewStatsBuilder().WithFinalKills(12).WithFinalDeaths(1).Build()).Build(),
			},
			wantOverallHigh: 8, // The extra 4 kills don't count toward the streak
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			got := computeFinalKillStreaks(ctx, tt.playerPITs)

			if len(tt.playerPITs) == 0 {
				require.Nil(t, got)
				return
			}
			require.NotNil(t, got)
			require.NotNil(t, got.Overall)

			require.Equal(t, tt.wantOverallHigh, got.Overall.Highest)
		})
	}
}

// Helper functions
func timePtr(t time.Time) *time.Time {
	return &t
}

func float64Ptr(f float64) *float64 {
	return &f
}

func intPtr(i int) *int {
	return &i
}

func TestComputePlaytimeDistribution(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	playerUUID := domaintest.NewUUID(t)

	oslo, err := time.LoadLocation("Europe/Oslo")
	require.NoError(t, err)
	newYork, err := time.LoadLocation("America/New_York")
	require.NoError(t, err)

	tests := []struct {
		name                    string
		sessions                []domain.Session
		location                *time.Location
		wantHourlyDistribution  [24]float64
		wantDayHourDistribution map[string][24]float64
		wantNil                 bool
	}{
		{
			name:     "single session within one hour",
			location: time.UTC,
			sessions: []domain.Session{
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 10, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(0).Build()).
						Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 10, 30, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(1).Build()).
						Build(),
				},
			},
			wantHourlyDistribution: func() [24]float64 {
				var arr [24]float64
				arr[10] = 0.5 // 30 minutes = 0.5 hours at hour 10
				return arr
			}(),
			wantDayHourDistribution: map[string][24]float64{
				"Sunday": {
					0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0,
					10: 0.5, // 30 minutes at hour 10
					11: 0, 12: 0, 13: 0, 14: 0, 15: 0, 16: 0, 17: 0, 18: 0, 19: 0,
					20: 0, 21: 0, 22: 0, 23: 0,
				},
			},
		},
		{
			name:     "single session spanning two hours",
			location: time.UTC,
			sessions: []domain.Session{
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 2, 14, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(0).Build()).
						Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 2, 16, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(1).Build()).
						Build(),
				},
			},
			wantHourlyDistribution: func() [24]float64 {
				var arr [24]float64
				arr[14] = 1.0 // hour 14: full hour
				arr[15] = 1.0 // hour 15: full hour
				return arr
			}(),
			wantDayHourDistribution: map[string][24]float64{
				"Monday": {
					0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0,
					10: 0, 11: 0, 12: 0, 13: 0,
					14: 1.0, // full hour
					15: 1.0, // full hour
					16: 0, 17: 0, 18: 0, 19: 0,
					20: 0, 21: 0, 22: 0, 23: 0,
				},
			},
		},
		{
			name:     "session spanning partial hours",
			location: time.UTC,
			sessions: []domain.Session{
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 3, 9, 30, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(0).Build()).
						Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 3, 11, 45, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(1).Build()).
						Build(),
				},
			},
			wantHourlyDistribution: func() [24]float64 {
				var arr [24]float64
				arr[9] = 0.5   // 9:30-10:00 = 30 min = 0.5 hours
				arr[10] = 1.0  // 10:00-11:00 = 1 hour
				arr[11] = 0.75 // 11:00-11:45 = 45 min = 0.75 hours
				return arr
			}(),
			wantDayHourDistribution: map[string][24]float64{
				"Tuesday": {
					0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0,
					9:  0.5,  // 30 minutes
					10: 1.0,  // full hour
					11: 0.75, // 45 minutes
					12: 0, 13: 0, 14: 0, 15: 0, 16: 0, 17: 0, 18: 0, 19: 0,
					20: 0, 21: 0, 22: 0, 23: 0,
				},
			},
		},
		{
			name:     "multiple sessions on different days",
			location: time.UTC,
			sessions: []domain.Session{
				{
					// Sunday session
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 10, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(0).Build()).
						Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 12, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(1).Build()).
						Build(),
				},
				{
					// Monday session at the same hour
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 2, 10, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(1).Build()).
						Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 2, 11, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(2).Build()).
						Build(),
				},
			},
			wantHourlyDistribution: func() [24]float64 {
				var arr [24]float64
				arr[10] = 2.0 // 1 hour on Sunday + 1 hour on Monday
				arr[11] = 1.0 // 1 hour on Sunday
				return arr
			}(),
			wantDayHourDistribution: map[string][24]float64{
				"Sunday": {
					0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0,
					10: 1.0, // 1 hour
					11: 1.0, // 1 hour
					12: 0, 13: 0, 14: 0, 15: 0, 16: 0, 17: 0, 18: 0, 19: 0,
					20: 0, 21: 0, 22: 0, 23: 0,
				},
				"Monday": {
					0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0,
					10: 1.0, // 1 hour
					11: 0, 12: 0, 13: 0, 14: 0, 15: 0, 16: 0, 17: 0, 18: 0, 19: 0,
					20: 0, 21: 0, 22: 0, 23: 0,
				},
			},
		},
		{
			name:     "session crossing midnight",
			location: time.UTC,
			sessions: []domain.Session{
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 1, 23, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(0).Build()).
						Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 2, 1, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(1).Build()).
						Build(),
				},
			},
			wantHourlyDistribution: func() [24]float64 {
				var arr [24]float64
				arr[23] = 1.0 // hour 23 (Sunday)
				arr[0] = 1.0  // hour 0 (Monday)
				return arr
			}(),
			wantDayHourDistribution: map[string][24]float64{
				"Sunday": {
					0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0,
					10: 0, 11: 0, 12: 0, 13: 0, 14: 0, 15: 0, 16: 0, 17: 0, 18: 0, 19: 0,
					20: 0, 21: 0, 22: 0,
					23: 1.0, // 1 hour
				},
				"Monday": {
					0: 1.0, // 1 hour
					1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0,
					10: 0, 11: 0, 12: 0, 13: 0, 14: 0, 15: 0, 16: 0, 17: 0, 18: 0, 19: 0,
					20: 0, 21: 0, 22: 0, 23: 0,
				},
			},
		},
		{
			name:     "timezone Europe/Oslo - session at noon UTC becomes 1PM/2PM local",
			location: oslo,
			sessions: []domain.Session{
				{
					// Summer time (CEST, UTC+2)
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.June, 15, 12, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(0).Build()).
						Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.June, 15, 14, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(1).Build()).
						Build(),
				},
				{
					// Winter time (CET, UTC+1)
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.December, 15, 8, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(0).Build()).
						Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.December, 15, 9, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(1).Build()).
						Build(),
				},
			},
			wantHourlyDistribution: func() [24]float64 {
				var arr [24]float64
				arr[9] = 1.0  // 8UTC = 9 CET (UTC+1 in winter)
				arr[14] = 1.0 // 12UTC = 14 CEST (UTC+2 in summer)
				arr[15] = 1.0 // 13UTC = 15 CEST
				return arr
			}(),
			wantDayHourDistribution: map[string][24]float64{
				"Thursday": {
					0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0,
					10: 0, 11: 0, 12: 0, 13: 0,
					14: 1.0, // 12UTC = 14 CEST
					15: 1.0, // 13UTC = 15 CEST
					16: 0, 17: 0, 18: 0, 19: 0,
					20: 0, 21: 0, 22: 0, 23: 0,
				},
				"Friday": {
					0: 0, 1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0,
					9:  1, // 8UTC = 9 CET
					10: 0, 11: 0, 12: 0, 13: 0, 14: 0, 15: 0, 16: 0, 17: 0,
					18: 0, 19: 0, 20: 0, 21: 0, 22: 0, 23: 0,
				},
			},
		},
		{
			name:     "timezone America/New_York - session at 6AM UTC becomes 1AM/2AM EST",
			location: newYork,
			sessions: []domain.Session{
				{
					Start: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 10, 6, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(0).Build()).
						Build(),
					End: domaintest.NewPlayerBuilder(playerUUID, time.Date(2023, time.January, 10, 8, 0, 0, 0, time.UTC)).
						WithOverallStats(domaintest.NewStatsBuilder().WithGamesPlayed(1).Build()).
						Build(),
				},
			},
			wantHourlyDistribution: func() [24]float64 {
				var arr [24]float64
				arr[1] = 1.0 // 6UTC = 1AM EST (UTC-5)
				arr[2] = 1.0 // 7UTC = 2AM EST
				return arr
			}(),
			wantDayHourDistribution: map[string][24]float64{
				"Tuesday": {
					0: 0,
					1: 1.0, // 6UTC = 1AM EST
					2: 1.0, // 7UTC = 2AM EST
					3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0,
					10: 0, 11: 0, 12: 0, 13: 0, 14: 0, 15: 0, 16: 0, 17: 0, 18: 0, 19: 0,
					20: 0, 21: 0, 22: 0, 23: 0,
				},
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			require.NotNil(t, tt.location)

			// So we don't have to fill in all days of the week in every test case
			for day := time.Sunday; day <= time.Saturday; day++ {
				if _, exists := tt.wantDayHourDistribution[day.String()]; !exists {
					tt.wantDayHourDistribution[day.String()] = [24]float64{}
				}
			}

			got := computePlaytimeDistribution(ctx, tt.sessions, tt.location)
			require.Equal(t, tt.wantHourlyDistribution, got.HourlyDistribution, "hourly distribution mismatch")
			require.Equal(t, tt.wantDayHourDistribution, got.DayHourDistribution, "day-hour distribution mismatch")
		})
	}
}
