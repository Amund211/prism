import { queryClient } from "#queryClient.ts";
import { getUsernameQueryOptions } from "#queries/username.ts";
import { getWrappedQueryOptions, type WrappedData } from "#queries/wrapped.ts";
import { type Session } from "#queries/sessions.ts";
import { useUUIDToUsername } from "#queries/username.ts";
import { computeStat } from "#stats/index.ts";
import {
    Box,
    Button,
    Card,
    CardContent,
    Chip,
    Divider,
    Grid,
    LinearProgress,
    Stack,
    Tooltip,
    Typography,
    Alert,
    ThemeProvider,
    createTheme,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link, Navigate } from "@tanstack/react-router";
import React, { type JSX } from "react";
import { usePlayerVisits } from "#contexts/PlayerVisits/hooks.ts";
import { normalizeUUID } from "#helpers/uuid.ts";
import { captureException } from "@sentry/react";
import { wrappedSearchSchema } from "#schemas/wrappedSearch.ts";
import { UserSearch } from "#components/UserSearch.tsx";
import {
    EmojiEvents,
    Star,
    TrendingUp,
    Celebration,
    Timer,
    LocalFireDepartment,
    Whatshot,
    EmojiEventsOutlined,
    Schedule,
    CalendarMonth,
    ShowChart,
    Warning,
    CheckCircle,
    Info,
    Error,
    PieChart,
    Download,
} from "@mui/icons-material";
import type { StatKey } from "#stats/keys.ts";
import { PlayerHead } from "#components/player.tsx";
import { ExportImageMount } from "#helpers/exportImage.tsx";

const getDefaultTimeZone = (): string => {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
};

export const Route = createFileRoute("/wrapped/$uuid")({
    loaderDeps: ({ search: { year } }) => {
        return { year };
    },
    loader: ({ params: { uuid: rawUUID }, deps: { year } }) => {
        const uuid = normalizeUUID(rawUUID);
        if (!uuid) return;

        Promise.all([
            queryClient.fetchQuery(
                getWrappedQueryOptions({
                    uuid,
                    year,
                    timezone: getDefaultTimeZone(),
                }),
            ),
            queryClient.fetchQuery(getUsernameQueryOptions(uuid)),
        ]).catch((error: unknown) => {
            captureException(error, {
                extra: {
                    uuid,
                    year,
                    message: "Failed to fetch wrapped + username data",
                },
            });
        });
    },
    validateSearch: wrappedSearchSchema,
    component: RouteComponent,
});

interface StatCardProps {
    title: string;
    value: string | number;
    subtitle?: string;
    icon?: JSX.Element;
    color?: string;
}

const StatCard: React.FC<StatCardProps> = ({
    title,
    value,
    subtitle,
    icon,
    color = "primary.main",
}) => {
    return (
        <Card
            variant="outlined"
            sx={{
                height: "100%",
                background: `linear-gradient(135deg, ${color}22 0%, ${color}11 100%)`,
                border: `2px solid ${color}`,
                transition: "all 0.3s ease",
                "&:hover": {
                    transform: "translateY(-8px) scale(1.02)",
                    boxShadow: `0 8px 24px ${color}44`,
                },
            }}
        >
            <CardContent>
                <Stack gap={1} alignItems="center" justifyContent="center">
                    {icon && <Box sx={{ color }}>{icon}</Box>}
                    <Typography
                        variant="subtitle2"
                        color="textSecondary"
                        textAlign="center"
                    >
                        {title}
                    </Typography>
                    <Typography
                        variant="h4"
                        fontWeight="bold"
                        textAlign="center"
                        sx={{
                            background: `linear-gradient(45deg, ${color}, ${color}dd)`,
                            backgroundClip: "text",
                            textFillColor: "transparent",
                        }}
                    >
                        {value}
                    </Typography>
                    {subtitle && (
                        <Typography
                            variant="caption"
                            color="textSecondary"
                            textAlign="center"
                        >
                            {subtitle}
                        </Typography>
                    )}
                </Stack>
            </CardContent>
        </Card>
    );
};

const formatHours = (hours: number): string => {
    if (hours < 1) {
        const minutes = Math.round(hours * 60);
        return `${minutes.toString()}m`;
    }
    const wholeHours = Math.floor(hours);
    const minutes = Math.round((hours - wholeHours) * 60);
    if (minutes === 0) {
        return `${wholeHours.toString()}h`;
    }
    return `${wholeHours.toString()}h ${minutes.toString()}m`;
};

const renderHour = (hour: number): string => {
    return new Date(2000, 0, 1, hour).toLocaleTimeString(undefined, {
        hour: "numeric",
    });
};

const DAYS = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
] as const;
type Day = (typeof DAYS)[number];

const renderDay = (day: Day): string => {
    const index = DAYS.indexOf(day);
    return new Date(
        2026,
        0,
        // January 5, 2026 is a Monday
        5 + index,
    ).toLocaleDateString(undefined, {
        weekday: "short",
    });
};

const reducedMotion = window.matchMedia(
    "(prefers-reduced-motion: reduce)",
).matches;

const ConfettiEffect: React.FC = () => {
    const [confetti, setConfetti] = React.useState<
        {
            id: number;
            left: number;
            delay: number;
            duration: number;
            hue: number;
            rotation: number;
        }[]
    >([]);
    const [showConfetti, setShowConfetti] = React.useState(true);

    React.useEffect(() => {
        const pieces = Array.from({ length: 50 }, (_, i) => ({
            id: i,
            left: Math.random() * 100,
            delay: Math.random() * 2,
            duration: 3 + Math.random() * 2,
            hue: Math.random() * 360,
            rotation: 360 + Math.random() * 360,
        }));
        setConfetti(pieces);
    }, []);

    React.useEffect(() => {
        const timer = setTimeout(() => {
            setShowConfetti(false);
        }, 10_000);
        return () => {
            clearTimeout(timer);
        };
    }, []);

    if (reducedMotion) return null;

    if (!showConfetti) return null;

    return (
        <Box
            sx={{
                position: "fixed",
                top: 0,
                left: 0,
                width: "100%",
                height: "100%",
                pointerEvents: "none",
                zIndex: 9999,
                overflow: "hidden",
            }}
        >
            {confetti.map((piece) => (
                <Box
                    key={piece.id}
                    sx={{
                        position: "absolute",
                        top: "-10px",
                        left: `${piece.left.toString()}%`,
                        width: "10px",
                        height: "10px",
                        backgroundColor: `hsl(${piece.hue.toString()}, 70%, 60%)`,
                        animation: `fall ${piece.duration.toString()}s linear ${piece.delay.toString()}s 1`,
                        "@keyframes fall": {
                            "0%": {
                                transform: "translateY(0) rotate(0deg)",
                                opacity: 1,
                            },
                            "100%": {
                                transform: `translateY(100vh) rotate(${piece.rotation.toString()}deg)`,
                                opacity: 0,
                            },
                        },
                    }}
                />
            ))}
        </Box>
    );
};

interface BestSessionCardProps {
    title: string;
    icon: JSX.Element;
    session: Session | undefined;
    statLabel: string;
    statType:
        | "fkdr"
        | "kills"
        | "finals"
        | "wins"
        | "duration"
        | "winsPerHour"
        | "finalsPerHour";
    color: string;
    showDuration?: boolean;
}

const BestSessionCard: React.FC<BestSessionCardProps> = ({
    title,
    icon,
    session,
    statLabel,
    statType,
    color,
    showDuration = true,
}) => {
    if (!session) return null;

    const startDate = new Date(session.start.queriedAt);
    const endDate = new Date(session.end.queriedAt);

    // Calculate session duration in hours
    const durationMs = endDate.getTime() - startDate.getTime();
    const durationHours = durationMs / (1000 * 60 * 60);

    const { start, end } = session;
    const history = [start];

    const gamesPlayed = computeStat(
        end,
        "overall",
        "gamesPlayed",
        "session",
        history,
    );
    const wins = computeStat(end, "overall", "wins", "session", history);
    const finalKills = computeStat(
        end,
        "overall",
        "finalKills",
        "session",
        history,
    );

    // Calculate the display value based on stat type
    let displayValue: number;
    switch (statType) {
        case "fkdr":
            displayValue = computeStat(
                end,
                "overall",
                "fkdr",
                "session",
                history,
            );
            break;
        case "kills":
            displayValue = computeStat(
                end,
                "overall",
                "kills",
                "session",
                history,
            );
            break;
        case "finals":
            displayValue = finalKills;
            break;
        case "wins":
            displayValue = wins;
            break;
        case "duration":
            displayValue = durationHours;
            break;
        case "winsPerHour":
            displayValue = durationHours > 0 ? wins / durationHours : 0;
            break;
        case "finalsPerHour":
            displayValue = durationHours > 0 ? finalKills / durationHours : 0;
            break;
    }

    return (
        <Card
            variant="outlined"
            sx={{
                background: `linear-gradient(135deg, ${color}22 0%, ${color}11 100%)`,
                border: `2px solid ${color}`,
            }}
        >
            <CardContent>
                <Stack gap={2}>
                    <Stack
                        direction="row"
                        gap={1}
                        alignItems="center"
                        justifyContent="center"
                    >
                        <Box sx={{ color, fontSize: 32 }}>{icon}</Box>
                        <Typography variant="h6" fontWeight="bold">
                            {title}
                        </Typography>
                    </Stack>
                    <Typography
                        variant="body2"
                        textAlign="center"
                        color="textSecondary"
                    >
                        {startDate.toLocaleDateString(undefined, {
                            month: "long",
                            day: "numeric",
                            year: "numeric",
                        })}
                    </Typography>
                    <Typography
                        variant="h4"
                        textAlign="center"
                        fontWeight="bold"
                    >
                        {displayValue.toLocaleString(undefined, {
                            maximumFractionDigits: 2,
                        })}{" "}
                        {statLabel}
                    </Typography>
                    <Stack
                        direction="row"
                        gap={2}
                        justifyContent="center"
                        flexWrap="wrap"
                    >
                        <Typography variant="caption" color="textSecondary">
                            {gamesPlayed.toLocaleString()} games
                        </Typography>
                        <Typography variant="caption" color="textSecondary">
                            {wins.toLocaleString()} wins
                        </Typography>
                        <Typography variant="caption" color="textSecondary">
                            {finalKills.toLocaleString()} finals
                        </Typography>
                        {showDuration && (
                            <Typography variant="caption" color="textSecondary">
                                {formatHours(durationHours)}
                            </Typography>
                        )}
                    </Stack>
                </Stack>
            </CardContent>
        </Card>
    );
};

interface SessionOverviewProps {
    wrappedData: WrappedData;
}

const SessionOverview: React.FC<SessionOverviewProps> = ({ wrappedData }) => {
    const sessionStats = wrappedData.sessionStats;
    if (!sessionStats) {
        return null;
    }

    const maxSessionsPerMonth = Math.max(
        ...Object.values(sessionStats.sessionsPerMonth),
        1,
    );

    return (
        <Card variant="outlined">
            <CardContent>
                <Stack gap={2}>
                    <Stack direction="row" alignItems="center" gap={1}>
                        <Schedule color="action" />
                        <Typography variant="h6">Session Overview</Typography>
                    </Stack>
                    <Grid container spacing={2}>
                        <Grid size={{ xs: 6, sm: 3 }}>
                            <Stack alignItems="center">
                                <Typography variant="h4" color="primary">
                                    {wrappedData.totalSessions.toLocaleString()}
                                </Typography>
                                <Typography
                                    variant="caption"
                                    color="textSecondary"
                                >
                                    Total Sessions
                                </Typography>
                            </Stack>
                        </Grid>
                        <Grid size={{ xs: 6, sm: 3 }}>
                            <Tooltip title="These sessions had gaps in tracking and were excluded">
                                <Stack alignItems="center">
                                    <Typography
                                        variant="h4"
                                        color="warning.main"
                                    >
                                        {wrappedData.nonConsecutiveSessions.toLocaleString()}
                                    </Typography>
                                    <Stack
                                        direction="row"
                                        alignItems="center"
                                        gap={0.5}
                                    >
                                        <Info fontSize="small" />
                                        <Typography
                                            variant="caption"
                                            color="textSecondary"
                                        >
                                            Filtered Out
                                        </Typography>
                                    </Stack>
                                </Stack>
                            </Tooltip>
                        </Grid>
                        <Grid size={{ xs: 6, sm: 3 }}>
                            <Stack alignItems="center">
                                <Typography variant="h4" color="success.main">
                                    {formatHours(
                                        sessionStats.sessionLengths.totalHours,
                                    )}
                                </Typography>
                                <Typography
                                    variant="caption"
                                    color="textSecondary"
                                >
                                    Total Time
                                </Typography>
                            </Stack>
                        </Grid>
                        <Grid size={{ xs: 6, sm: 3 }}>
                            <Stack alignItems="center">
                                <Typography variant="h4" color="info.main">
                                    {formatHours(
                                        sessionStats.sessionLengths
                                            .averageHours,
                                    )}
                                </Typography>
                                <Typography
                                    variant="caption"
                                    color="textSecondary"
                                >
                                    Avg. Session
                                </Typography>
                            </Stack>
                        </Grid>
                    </Grid>

                    <Divider />

                    <Typography variant="subtitle2">
                        Sessions per Month
                    </Typography>
                    <Grid container spacing={1}>
                        {[
                            "Jan",
                            "Feb",
                            "Mar",
                            "Apr",
                            "May",
                            "Jun",
                            "Jul",
                            "Aug",
                            "Sep",
                            "Oct",
                            "Nov",
                            "Dec",
                        ].map((month, index) => {
                            const count =
                                sessionStats.sessionsPerMonth[
                                    (index + 1).toString()
                                ] ?? 0;
                            return (
                                <Grid
                                    size={{
                                        xs: 1,
                                    }}
                                    key={month}
                                >
                                    <Tooltip
                                        title={`${count.toLocaleString()} sessions`}
                                    >
                                        <Stack alignItems="center" gap={0.5}>
                                            <Typography
                                                variant="caption"
                                                color="textSecondary"
                                            >
                                                {month}
                                            </Typography>
                                            <Chip
                                                label={count.toLocaleString()}
                                                size="small"
                                                color={
                                                    count > 0
                                                        ? "primary"
                                                        : "default"
                                                }
                                            />
                                        </Stack>
                                    </Tooltip>
                                </Grid>
                            );
                        })}
                    </Grid>

                    {/* Bar chart for sessions per month */}
                    <Box sx={{ mt: 2, mb: 1 }}>
                        <Grid container spacing={1}>
                            {[
                                "Jan",
                                "Feb",
                                "Mar",
                                "Apr",
                                "May",
                                "Jun",
                                "Jul",
                                "Aug",
                                "Sep",
                                "Oct",
                                "Nov",
                                "Dec",
                            ].map((month, index) => {
                                const count =
                                    sessionStats.sessionsPerMonth[
                                        (index + 1).toString()
                                    ] ?? 0;
                                const heightPercent =
                                    (count / maxSessionsPerMonth) * 100;
                                return (
                                    <Grid
                                        size={{
                                            xs: 1,
                                        }}
                                        key={`bar-${month}`}
                                    >
                                        <Tooltip
                                            title={`${count.toLocaleString()} sessions`}
                                        >
                                            <Box
                                                sx={{
                                                    display: "flex",
                                                    flexDirection: "column",
                                                    alignItems: "center",
                                                    height: 60,
                                                    justifyContent: "flex-end",
                                                }}
                                            >
                                                <Box
                                                    sx={{
                                                        width: "100%",
                                                        height: `${heightPercent.toString()}%`,
                                                        bgcolor:
                                                            count > 0
                                                                ? "primary.main"
                                                                : "action.disabled",
                                                        borderRadius:
                                                            "4px 4px 0 0",
                                                        minHeight:
                                                            count > 0
                                                                ? "4px"
                                                                : "2px",
                                                    }}
                                                />
                                            </Box>
                                        </Tooltip>
                                    </Grid>
                                );
                            })}
                        </Grid>
                    </Box>
                </Stack>
            </CardContent>
        </Card>
    );
};

interface YearStatsCardsProps {
    wrappedData: WrappedData & {
        yearStats: NonNullable<WrappedData["yearStats"]>;
    };
}

const YearStatsCards: React.FC<YearStatsCardsProps> = ({ wrappedData }) => {
    const getOverallSessionStats = (
        stat: Exclude<StatKey, "winstreak">,
    ): number => {
        return computeStat(
            wrappedData.yearStats.end,
            "overall",
            stat,
            "session",
            [wrappedData.yearStats.start],
        );
    };
    const getCurrentStats = (stat: Exclude<StatKey, "winstreak">): number => {
        return computeStat(
            wrappedData.yearStats.end,
            "overall",
            stat,
            "overall",
            [],
        );
    };

    const totalGames = getOverallSessionStats("gamesPlayed");
    const totalWins = getOverallSessionStats("wins");

    const totalFinalKills = getOverallSessionStats("finalKills");
    const yearlyFKDR = computeStat(
        wrappedData.yearStats.end,
        "overall",
        "fkdr",
        "session",
        [wrappedData.yearStats.start],
    );

    const totalBedsBroken = getOverallSessionStats("bedsBroken");
    const totalBedsLost = getOverallSessionStats("bedsLost");
    const yearlyBBLR =
        totalBedsLost !== 0 ? totalBedsBroken / totalBedsLost : totalBedsBroken;

    const totalStars = getOverallSessionStats("stars");
    const eoyStars = getCurrentStats("stars");

    const soyFKDR = computeStat(
        wrappedData.yearStats.start,
        "overall",
        "fkdr",
        "overall",
        [],
    );
    const eoyFKDR = getCurrentStats("fkdr");
    const fkdrGained = eoyFKDR - soyFKDR;

    const winRate = totalGames !== 0 ? (totalWins / totalGames) * 100 : 0;
    return (
        <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                <StatCard
                    title="Games Played"
                    value={totalGames.toLocaleString()}
                    subtitle={
                        wrappedData.sessionStats?.sessionCoverage
                            ? `${wrappedData.sessionStats.sessionCoverage.gamesPlayedPercentage.toLocaleString(undefined, { maximumFractionDigits: 1 })}% in sessions`
                            : undefined
                    }
                    icon={<EmojiEvents sx={{ fontSize: 48 }} />}
                    color="#FF6B6B"
                />
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                <StatCard
                    title="Wins"
                    value={totalWins.toLocaleString()}
                    subtitle={`${winRate.toLocaleString(undefined, { maximumFractionDigits: 1 })}% win rate`}
                    icon={<Star sx={{ fontSize: 48 }} />}
                    color="#4ECDC4"
                />
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                <StatCard
                    title="Final Kills"
                    value={totalFinalKills.toLocaleString()}
                    subtitle={`${yearlyFKDR.toLocaleString(undefined, { maximumFractionDigits: 2 })} yearly FKDR`}
                    icon={<Whatshot sx={{ fontSize: 48 }} />}
                    color="#FFD93D"
                />
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                <StatCard
                    title="Beds Broken"
                    value={totalBedsBroken.toLocaleString()}
                    subtitle={`${yearlyBBLR.toLocaleString(undefined, { maximumFractionDigits: 2 })} yearly BBLR`}
                    icon={<Celebration sx={{ fontSize: 48 }} />}
                    color="#95E1D3"
                />
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                <StatCard
                    title="FKDR"
                    value={eoyFKDR.toLocaleString(undefined, {
                        maximumFractionDigits: 2,
                    })}
                    subtitle={fkdrGained.toLocaleString(undefined, {
                        signDisplay: "always",
                        maximumFractionDigits: 2,
                    })}
                    icon={<TrendingUp sx={{ fontSize: 48 }} />}
                    color="#A8E6CF"
                />
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 4 }}>
                <StatCard
                    title="Stars Gained"
                    value={`+${totalStars.toLocaleString(undefined, { maximumFractionDigits: 1 })}`}
                    subtitle={`now at ${eoyStars.toLocaleString(undefined, { maximumFractionDigits: 1 })} ⭐`}
                    icon={<Star sx={{ fontSize: 48 }} />}
                    color="#FFB6D9"
                />
            </Grid>
        </Grid>
    );
};

interface AverageSessionStatsProps {
    wrappedData: WrappedData;
}

const AverageSessionStats: React.FC<AverageSessionStatsProps> = ({
    wrappedData,
}) => {
    const sessionStats = wrappedData.sessionStats;
    if (!sessionStats?.averages) return null;

    return (
        <Card variant="outlined" sx={{ height: "100%" }}>
            <CardContent>
                <Stack gap={2}>
                    <Stack direction="row" alignItems="center" gap={1}>
                        <ShowChart color="action" />
                        <Typography variant="h6">
                            Average Session Stats
                        </Typography>
                    </Stack>
                    <Grid container spacing={2}>
                        <Grid size={{ xs: 6, sm: 3 }}>
                            <Stack alignItems="center">
                                <Typography variant="h5" color="primary">
                                    {sessionStats.averages.gamesPlayed.toLocaleString(
                                        undefined,
                                        { maximumFractionDigits: 1 },
                                    )}
                                </Typography>
                                <Typography
                                    variant="caption"
                                    color="textSecondary"
                                >
                                    Games/Session
                                </Typography>
                            </Stack>
                        </Grid>
                        <Grid size={{ xs: 6, sm: 3 }}>
                            <Stack alignItems="center">
                                <Typography variant="h5" color="success.main">
                                    {sessionStats.averages.wins.toLocaleString(
                                        undefined,
                                        { maximumFractionDigits: 1 },
                                    )}
                                </Typography>
                                <Typography
                                    variant="caption"
                                    color="textSecondary"
                                >
                                    Wins/Session
                                </Typography>
                            </Stack>
                        </Grid>
                        <Grid size={{ xs: 6, sm: 3 }}>
                            <Stack alignItems="center">
                                <Typography variant="h5" color="warning.main">
                                    {sessionStats.averages.finalKills.toLocaleString(
                                        undefined,
                                        { maximumFractionDigits: 1 },
                                    )}
                                </Typography>
                                <Typography
                                    variant="caption"
                                    color="textSecondary"
                                >
                                    Finals/Session
                                </Typography>
                            </Stack>
                        </Grid>
                        <Grid size={{ xs: 6, sm: 3 }}>
                            <Stack alignItems="center">
                                <Typography variant="h5" color="info.main">
                                    {formatHours(
                                        sessionStats.averages
                                            .sessionLengthHours,
                                    )}
                                </Typography>
                                <Typography
                                    variant="caption"
                                    color="textSecondary"
                                >
                                    Avg Length
                                </Typography>
                            </Stack>
                        </Grid>
                    </Grid>
                </Stack>
            </CardContent>
        </Card>
    );
};

interface BestSessionsProps {
    wrappedData: WrappedData;
}

const BestSessions: React.FC<BestSessionsProps> = ({ wrappedData }) => {
    const sessionStats = wrappedData.sessionStats;
    if (!sessionStats?.bestSessions) return null;

    return (
        <>
            <Typography variant="h5" fontWeight="bold" sx={{ mt: 3 }}>
                🏆 Best Sessions
            </Typography>

            <Grid container spacing={2}>
                <Grid size={{ xs: 6, md: 4 }}>
                    <BestSessionCard
                        title="Highest FKDR"
                        icon={<TrendingUp />}
                        session={sessionStats.bestSessions.highestFKDR}
                        statLabel="FKDR"
                        statType="fkdr"
                        color="#667eea"
                    />
                </Grid>
                <Grid size={{ xs: 6, md: 4 }}>
                    <BestSessionCard
                        title="Most Kills"
                        icon={<LocalFireDepartment />}
                        session={sessionStats.bestSessions.mostKills}
                        statLabel="Kills"
                        statType="kills"
                        color="#f093fb"
                    />
                </Grid>
                <Grid size={{ xs: 6, md: 4 }}>
                    <BestSessionCard
                        title="Most Final Kills"
                        icon={<Whatshot />}
                        session={sessionStats.bestSessions.mostFinalKills}
                        statLabel="Final Kills"
                        statType="finals"
                        color="#FFD93D"
                    />
                </Grid>
                <Grid size={{ xs: 6, md: 4 }}>
                    <BestSessionCard
                        title="Most Wins"
                        icon={<EmojiEventsOutlined />}
                        session={sessionStats.bestSessions.mostWins}
                        statLabel="Wins"
                        statType="wins"
                        color="#4ECDC4"
                    />
                </Grid>
                <Grid size={{ xs: 6, md: 4 }}>
                    <BestSessionCard
                        title="Longest Session"
                        icon={<Timer />}
                        session={sessionStats.bestSessions.longestSession}
                        statLabel="hours"
                        statType="duration"
                        color="#A8E6CF"
                        showDuration={false}
                    />
                </Grid>
                <Grid size={{ xs: 6, md: 4 }}>
                    <BestSessionCard
                        title="Most Wins/Hour"
                        icon={<TrendingUp />}
                        session={sessionStats.bestSessions.mostWinsPerHour}
                        statLabel="wins/hr"
                        statType="winsPerHour"
                        color="#95E1D3"
                    />
                </Grid>
                <Grid size={{ xs: 6, md: 4 }}>
                    <BestSessionCard
                        title="Most Finals/Hour"
                        icon={<Whatshot />}
                        session={sessionStats.bestSessions.mostFinalsPerHour}
                        statLabel="finals/hr"
                        statType="finalsPerHour"
                        color="#FF6B6B"
                    />
                </Grid>
            </Grid>
        </>
    );
};

interface StreaksProps {
    wrappedData: WrappedData;
}

const Streaks: React.FC<StreaksProps> = ({ wrappedData }) => {
    const sessionStats = wrappedData.sessionStats;
    if (!sessionStats) return null;

    const modes = ["overall", "solo", "doubles", "threes", "fours"] as const;

    return (
        <>
            <Typography variant="h5" fontWeight="bold" sx={{ mt: 3 }}>
                🔥 Streaks
            </Typography>

            <Grid container spacing={2}>
                <Grid size={{ xs: 12, md: 6 }}>
                    <Card variant="outlined">
                        <CardContent>
                            <Stack gap={2}>
                                <Typography variant="h6" textAlign="center">
                                    Highest Ended Winstreaks
                                </Typography>
                                <Divider />
                                {modes.map((mode) => {
                                    const streak =
                                        sessionStats.winstreaks[mode];

                                    return (
                                        <Stack
                                            key={mode}
                                            direction="row"
                                            justifyContent="space-between"
                                            alignItems="center"
                                        >
                                            <Typography
                                                variant="body2"
                                                sx={{
                                                    textTransform: "capitalize",
                                                }}
                                            >
                                                {mode}
                                            </Typography>
                                            <Stack alignItems="flex-end">
                                                <Typography
                                                    variant="h6"
                                                    color="primary.main"
                                                >
                                                    {streak.highest.toLocaleString()}
                                                </Typography>
                                                <Typography
                                                    variant="caption"
                                                    color="textSecondary"
                                                >
                                                    {new Date(
                                                        streak.when,
                                                    ).toLocaleDateString(
                                                        undefined,
                                                        {
                                                            month: "short",
                                                            day: "numeric",
                                                        },
                                                    )}
                                                </Typography>
                                            </Stack>
                                        </Stack>
                                    );
                                })}
                            </Stack>
                        </CardContent>
                    </Card>
                </Grid>

                <Grid size={{ xs: 12, md: 6 }}>
                    <Card variant="outlined">
                        <CardContent>
                            <Stack gap={2}>
                                <Stack
                                    direction="row"
                                    alignItems="center"
                                    justifyContent="center"
                                    gap={1}
                                >
                                    <Typography variant="h6">
                                        Highest Ended Final Kill Streaks
                                    </Typography>
                                    <Tooltip title="A final kill streak is the number of final kills in a row without taking a final death.">
                                        <Info color="info" fontSize="small" />
                                    </Tooltip>
                                </Stack>
                                <Divider />
                                {modes.map((mode) => {
                                    const streak =
                                        sessionStats.finalKillStreaks[mode];
                                    return (
                                        <Stack
                                            key={mode}
                                            direction="row"
                                            justifyContent="space-between"
                                            alignItems="center"
                                        >
                                            <Typography
                                                variant="body2"
                                                sx={{
                                                    textTransform: "capitalize",
                                                }}
                                            >
                                                {mode}
                                            </Typography>
                                            <Stack alignItems="flex-end">
                                                <Typography
                                                    variant="h6"
                                                    color="error.main"
                                                >
                                                    {streak.highest.toLocaleString()}
                                                </Typography>
                                                <Typography
                                                    variant="caption"
                                                    color="textSecondary"
                                                >
                                                    {new Date(
                                                        streak.when,
                                                    ).toLocaleDateString(
                                                        undefined,
                                                        {
                                                            month: "short",
                                                            day: "numeric",
                                                        },
                                                    )}
                                                </Typography>
                                            </Stack>
                                        </Stack>
                                    );
                                })}
                            </Stack>
                        </CardContent>
                    </Card>
                </Grid>
            </Grid>
        </>
    );
};

interface FavoritePlayTimesProps {
    wrappedData: WrappedData;
}

const FavoritePlayTimes: React.FC<FavoritePlayTimesProps> = ({
    wrappedData,
}) => {
    const sessionStats = wrappedData.sessionStats;
    if (!sessionStats?.playtimeDistribution) return null;

    const { hourlyDistribution, dayHourDistribution } =
        sessionStats.playtimeDistribution;

    const maxHourlyValue = Math.max(...hourlyDistribution, 0.01);
    const maxDayHourlyValue = Math.max(
        ...Object.values(dayHourDistribution).flat(),
        0.01,
    );

    // TODO: Use the tz from params or similar if we implement a selector
    const tz = getDefaultTimeZone();

    return (
        <Card variant="outlined">
            <CardContent>
                <Stack gap={2}>
                    <Stack direction="row" alignItems="center" gap={1}>
                        <CalendarMonth color="action" />
                        <Typography variant="h6">
                            {`Play Time Patterns (${tz})`}
                        </Typography>
                    </Stack>

                    {/* 24-hour bar chart using actual playtime distribution */}
                    <Box sx={{ mt: 2 }}>
                        <Typography
                            variant="caption"
                            color="textSecondary"
                            sx={{ mb: 1, display: "block" }}
                        >
                            Playtime distribution across the day
                        </Typography>
                        <Box
                            sx={{
                                display: "flex",
                                gap: 0.5,
                                alignItems: "flex-end",
                                height: 80,
                                // To align the bars with the heatmap below
                                // 70 px text for day labels + 0.5 (4px) gap
                                paddingLeft: "74px",
                            }}
                        >
                            {hourlyDistribution.map((hours, hour) => {
                                const heightPercent =
                                    (hours / maxHourlyValue) * 100;

                                return (
                                    <Tooltip
                                        key={hour}
                                        title={`${renderHour(hour)}:00 - ${renderHour((hour + 1) % 24)}:00: ${formatHours(hours)}`}
                                    >
                                        <Box
                                            sx={{
                                                flex: 1,
                                                display: "flex",
                                                flexDirection: "column",
                                                justifyContent: "flex-end",
                                                alignItems: "center",
                                                height: "100%",
                                            }}
                                        >
                                            <Box
                                                sx={{
                                                    width: "100%",
                                                    height: `${heightPercent.toString()}%`,
                                                    bgcolor:
                                                        hours > 0
                                                            ? "primary.main"
                                                            : "action.disabled",
                                                    borderRadius: "2px 2px 0 0",
                                                    minHeight:
                                                        hours > 0
                                                            ? "4px"
                                                            : "2px",
                                                    transition: "all 0.3s ease",
                                                    "&:hover": {
                                                        opacity: 0.8,
                                                    },
                                                }}
                                            />
                                        </Box>
                                    </Tooltip>
                                );
                            })}
                        </Box>
                        {/* Hour labels */}
                        <Box
                            sx={{
                                display: "flex",
                                gap: 0.25,
                                pt: 0.5,
                                ml: "74px",
                            }}
                        >
                            {Array.from({ length: 24 }).map((_, hour) =>
                                hour % 6 === 0 ? (
                                    <Typography
                                        key={hour}
                                        variant="caption"
                                        sx={{
                                            flex: 1,
                                            fontSize: "0.6rem",
                                            textAlign: "center",
                                        }}
                                    >
                                        {renderHour(hour)}
                                    </Typography>
                                ) : (
                                    <Box key={hour} sx={{ flex: 1 }} />
                                ),
                            )}
                        </Box>
                    </Box>

                    {/* Heatmap: day of week x hour of day */}
                    <Box sx={{ mt: 3 }}>
                        <Typography
                            variant="caption"
                            color="textSecondary"
                            sx={{ mb: 1, display: "block" }}
                        >
                            Playtime heatmap across the week
                        </Typography>
                        <Box
                            sx={{
                                display: "flex",
                                flexDirection: "column",
                                gap: 0.5,
                            }}
                        >
                            {(
                                [
                                    "Monday",
                                    "Tuesday",
                                    "Wednesday",
                                    "Thursday",
                                    "Friday",
                                    "Saturday",
                                    "Sunday",
                                ] as const
                            ).map((day) => {
                                const dayData = dayHourDistribution[day];

                                return (
                                    <Box
                                        key={day}
                                        sx={{
                                            display: "flex",
                                            gap: 0.5,
                                            alignItems: "center",
                                        }}
                                    >
                                        <Typography
                                            variant="caption"
                                            sx={{
                                                width: "70px",
                                                fontSize: "0.7rem",
                                            }}
                                        >
                                            {renderDay(day)}
                                        </Typography>
                                        <Box
                                            sx={{
                                                display: "flex",
                                                gap: 0.25,
                                                flex: 1,
                                            }}
                                        >
                                            {dayData.map((hours, hour) => {
                                                const intensity =
                                                    hours / maxDayHourlyValue;
                                                const opacity =
                                                    hours > 0
                                                        ? 0.2 + intensity * 0.8
                                                        : 0.05;

                                                return (
                                                    <Tooltip
                                                        key={hour}
                                                        title={`${renderDay(day)} ${renderHour(hour)}:00 - ${renderHour((hour + 1) % 24)}:00: ${formatHours(hours)}`}
                                                    >
                                                        <Box
                                                            sx={{
                                                                flex: 1,
                                                                height: 20,
                                                                bgcolor:
                                                                    "primary.main",
                                                                opacity:
                                                                    opacity,
                                                                borderRadius: 0.5,
                                                                transition:
                                                                    "all 0.2s ease",
                                                                "&:hover": {
                                                                    transform:
                                                                        "scale(1.2)",
                                                                    zIndex: 10,
                                                                    opacity: 1,
                                                                },
                                                            }}
                                                        />
                                                    </Tooltip>
                                                );
                                            })}
                                        </Box>
                                    </Box>
                                );
                            })}
                            {/* Hour labels */}
                            <Box
                                sx={{
                                    display: "flex",
                                    gap: 0.25,
                                    ml: "74px",
                                }}
                            >
                                {Array.from({ length: 24 }).map((_, hour) =>
                                    hour % 6 === 0 ? (
                                        <Typography
                                            key={hour}
                                            variant="caption"
                                            sx={{
                                                flex: 1,
                                                fontSize: "0.6rem",
                                                textAlign: "center",
                                            }}
                                        >
                                            {renderHour(hour)}
                                        </Typography>
                                    ) : (
                                        <Box key={hour} sx={{ flex: 1 }} />
                                    ),
                                )}
                            </Box>
                        </Box>
                    </Box>
                </Stack>
            </CardContent>
        </Card>
    );
};

interface FlawlessSessionsProps {
    wrappedData: WrappedData;
}

const FlawlessSessions: React.FC<FlawlessSessionsProps> = ({ wrappedData }) => {
    const sessionStats = wrappedData.sessionStats;
    if (!sessionStats?.flawlessSessions) return null;

    return (
        <Card
            variant="outlined"
            sx={{
                background:
                    "linear-gradient(135deg, #FFD70022 0%, #FFD70011 100%)",
                border: "2px solid #FFD700",
            }}
        >
            <CardContent>
                <Stack gap={2} alignItems="center">
                    <Stack direction="row" alignItems="center" gap={1}>
                        <CheckCircle
                            sx={{
                                fontSize: 32,
                                color: "#FFD700",
                            }}
                        />
                        <Typography variant="h5">Flawless Sessions</Typography>
                    </Stack>
                    <Typography variant="h3" fontWeight="bold" color="#FFD700">
                        {sessionStats.flawlessSessions.count.toLocaleString()}
                    </Typography>
                    <Typography variant="body2" color="textSecondary">
                        {sessionStats.flawlessSessions.percentage.toLocaleString(
                            undefined,
                            { maximumFractionDigits: 1 },
                        )}
                        % of sessions with no losses and no final deaths
                    </Typography>
                </Stack>
            </CardContent>
        </Card>
    );
};

interface ExportStatsCardProps {
    uuid: string;
    year: number;
    wrappedData: WrappedData & {
        yearStats: NonNullable<WrappedData["yearStats"]>;
    };
}

const ExportStatsCard: React.FC<ExportStatsCardProps> = ({
    uuid,
    year,
    wrappedData,
}) => {
    return (
        <ThemeProvider
            theme={() =>
                createTheme({
                    // Force theme and breakpoints for predictable rendering
                    palette: { mode: "dark" },
                    breakpoints: {
                        values: {
                            xs: 0,
                            sm: 0,
                            md: 0,
                            lg: 0,
                            xl: 1,
                        },
                    },
                })
            }
        >
            <Stack
                width="1600px"
                padding={4}
                gap={3}
                sx={{
                    background: (theme) => theme.palette.background.default,

                    // Never wrap whitespace, as that causes all typography to wrap their last word
                    // https://github.com/bubkoo/html-to-image/issues/132
                    whiteSpace: "nowrap",
                }}
            >
                <WrappedHeader
                    wrappedData={wrappedData}
                    uuid={uuid}
                    year={year}
                />
                {wrappedData.totalSessions === 0 ? (
                    <Alert severity="info" icon={<Info />}>
                        <Typography variant="body2">
                            This player didn&apos;t record any sessions with the
                            Prism Overlay in {year.toString()}. Showing overall
                            year statistics instead. Download it to start
                            tracking your stats!
                        </Typography>
                    </Alert>
                ) : (
                    <LowSessionCoverageAlert
                        coveragePercentage={
                            wrappedData.sessionStats?.sessionCoverage
                                .gamesPlayedPercentage
                        }
                    />
                )}
                <SessionOverview wrappedData={wrappedData} />

                <Grid container spacing={2}>
                    <Grid size={{ xs: 6 }}>
                        <SessionCoverage wrappedData={wrappedData} />
                    </Grid>
                    <Grid size={{ xs: 6 }}>
                        <AverageSessionStats wrappedData={wrappedData} />
                    </Grid>
                </Grid>

                {wrappedData.sessionStats && (
                    <Grid container spacing={2}>
                        <Grid size={{ xs: 4 }}>
                            <BestSessionCard
                                title="Highest FKDR"
                                icon={<TrendingUp />}
                                session={
                                    wrappedData.sessionStats.bestSessions
                                        .highestFKDR
                                }
                                statLabel="FKDR"
                                statType="fkdr"
                                color="#667eea"
                            />
                        </Grid>
                        <Grid size={{ xs: 4 }}>
                            <BestSessionCard
                                title="Most Final Kills"
                                icon={<Whatshot />}
                                session={
                                    wrappedData.sessionStats.bestSessions
                                        .mostFinalKills
                                }
                                statLabel="Final Kills"
                                statType="finals"
                                color="#FFD93D"
                            />
                        </Grid>
                        <Grid size={{ xs: 4 }}>
                            <BestSessionCard
                                title="Longest Session"
                                icon={<Timer />}
                                session={
                                    wrappedData.sessionStats.bestSessions
                                        .longestSession
                                }
                                statLabel="hours"
                                statType="duration"
                                color="#A8E6CF"
                                showDuration={false}
                            />
                        </Grid>
                    </Grid>
                )}

                <FlawlessSessions wrappedData={wrappedData} />

                <YearStatsCards wrappedData={wrappedData} />

                <Typography
                    variant="h6"
                    textAlign="center"
                    sx={{ color: "rgba(255, 255, 255, 0.9)" }}
                >
                    🎮 See more details and create your own at{" "}
                    <Typography
                        component="span"
                        variant="h6"
                        fontWeight="bold"
                        sx={{ color: "white" }}
                    >
                        prismoverlay.com/wrapped
                    </Typography>
                </Typography>
            </Stack>
        </ThemeProvider>
    );
};

interface SessionCoverageProps {
    wrappedData: WrappedData;
}

const SessionCoverage: React.FC<SessionCoverageProps> = ({ wrappedData }) => {
    const sessionStats = wrappedData.sessionStats;
    if (!sessionStats?.sessionCoverage) return null;

    return (
        <Card variant="outlined">
            <CardContent>
                <Stack gap={2}>
                    <Stack direction="row" alignItems="center" gap={1}>
                        <PieChart color="action" />
                        <Typography variant="h6">Session Coverage</Typography>
                    </Stack>
                    <Grid container spacing={2}>
                        <Grid size={{ xs: 12, sm: 6 }}>
                            <Stack alignItems="center">
                                <Typography variant="h4" color="primary">
                                    {sessionStats.sessionCoverage.gamesPlayedPercentage.toLocaleString(
                                        undefined,
                                        { maximumFractionDigits: 1 },
                                    )}
                                    %
                                </Typography>
                                <Typography
                                    variant="caption"
                                    color="textSecondary"
                                    textAlign="center"
                                >
                                    of games played captured in sessions
                                </Typography>
                            </Stack>
                        </Grid>
                        <Grid size={{ xs: 12, sm: 6 }}>
                            <Stack alignItems="center">
                                <Typography variant="h4" color="success.main">
                                    {formatHours(
                                        sessionStats.sessionCoverage
                                            .adjustedTotalHours,
                                    )}
                                </Typography>
                                <Typography
                                    variant="caption"
                                    color="textSecondary"
                                    textAlign="center"
                                >
                                    adjusted total playtime (accounting for
                                    games not in sessions)
                                </Typography>
                            </Stack>
                        </Grid>
                    </Grid>
                </Stack>
            </CardContent>
        </Card>
    );
};

function NoSessionsAlert({ year }: { year: number }) {
    return (
        <Alert severity="info" icon={<Info />}>
            <Typography variant="body2">
                This player didn&apos;t record any sessions with the Prism
                Overlay in {year.toString()}. Showing overall year statistics
                instead. Download it{" "}
                {
                    <Link to="/downloads" target="_blank">
                        here
                    </Link>
                }{" "}
                to start tracking your stats!
            </Typography>
        </Alert>
    );
}

function LowSessionCoverageAlert({
    coveragePercentage,
}: {
    coveragePercentage: number | undefined;
}) {
    const lowCoverage =
        coveragePercentage === undefined || coveragePercentage < 50;

    if (!lowCoverage) return null;

    return (
        <Alert severity="warning" icon={<Warning />}>
            <Typography variant="body2">
                Session coverage is low (
                {coveragePercentage?.toLocaleString(undefined, {
                    maximumFractionDigits: 1,
                }) ?? "0.0"}
                % of games in sessions). Session statistics may be inaccurate.
            </Typography>
        </Alert>
    );
}

interface WrappedStatsContentProps {
    wrappedData?:
        | WrappedData
        | (WrappedData & { yearStats: NonNullable<WrappedData["yearStats"]> });
    isLoading: boolean;
}

function WrappedStatsContent({
    wrappedData,
    isLoading,
}: WrappedStatsContentProps) {
    if (isLoading) {
        return (
            <Card variant="outlined">
                <CardContent>
                    <Typography variant="h6" textAlign="center">
                        Loading your year in review...
                    </Typography>
                    <LinearProgress sx={{ mt: 2 }} />
                </CardContent>
            </Card>
        );
    }

    if (!wrappedData) {
        return (
            <Card variant="outlined">
                <CardContent
                    component={Stack}
                    direction="row"
                    gap={2}
                    alignItems="center"
                    justifyContent="center"
                >
                    <Error color="error" />
                    <Typography variant="h6" textAlign="center">
                        Failed loading your year in review. Please try again
                        later.
                    </Typography>
                </CardContent>
            </Card>
        );
    }

    if (!wrappedData.yearStats) {
        return (
            <Alert severity="info" icon={<Info />}>
                <Typography variant="body2">
                    This player didn&apos;t record any stats with the Prism
                    Overlay in {wrappedData.year.toString()}. Download it{" "}
                    {
                        <Link to="/downloads" target="_blank">
                            here
                        </Link>
                    }{" "}
                    to start tracking your stats!
                </Typography>
            </Alert>
        );
    }

    const yearStatsCard = (
        <YearStatsCards
            // Ugly hack for TS to understand that yearStats is defined
            wrappedData={{ ...wrappedData, yearStats: wrappedData.yearStats }}
        />
    );

    if (wrappedData.totalSessions === 0) {
        return (
            <>
                <NoSessionsAlert year={wrappedData.year} />
                {yearStatsCard}
            </>
        );
    }

    return (
        <>
            <LowSessionCoverageAlert
                coveragePercentage={
                    wrappedData.sessionStats?.sessionCoverage
                        .gamesPlayedPercentage
                }
            />

            <SessionOverview wrappedData={wrappedData} />

            <Grid container spacing={2}>
                <Grid size={{ xs: 12, lg: 6 }}>
                    <SessionCoverage wrappedData={wrappedData} />
                </Grid>
                <Grid size={{ xs: 12, lg: 6 }}>
                    <AverageSessionStats wrappedData={wrappedData} />
                </Grid>
            </Grid>

            {yearStatsCard}

            <BestSessions wrappedData={wrappedData} />

            <Streaks wrappedData={wrappedData} />

            <FavoritePlayTimes wrappedData={wrappedData} />

            <FlawlessSessions wrappedData={wrappedData} />
        </>
    );
}

interface WrappedHeaderProps {
    wrappedData?:
        | WrappedData
        | (WrappedData & { yearStats: NonNullable<WrappedData["yearStats"]> });
    uuid: string;
    year: number;
}

function WrappedHeader({ wrappedData, uuid, year }: WrappedHeaderProps) {
    const username = useUUIDToUsername([uuid])[uuid];
    const dateRangeString = wrappedData?.yearStats
        ? `Based on stats from ${wrappedData.yearStats.start.queriedAt.toLocaleDateString(
              undefined,
              {
                  month: "short",
                  day: "numeric",
                  year: "numeric",
              },
          )} → ${wrappedData.yearStats.end.queriedAt.toLocaleDateString(
              undefined,
              {
                  month: "short",
                  day: "numeric",
                  year: "numeric",
              },
          )}.`
        : undefined;

    return (
        <Stack
            direction="row"
            gap={2}
            alignItems="center"
            justifyContent="center"
        >
            <PlayerHead
                uuid={uuid}
                username={username}
                variant="face"
                width={80}
            />
            <Stack alignItems="center">
                <Typography
                    variant="h3"
                    fontWeight="bold"
                    textAlign="center"
                    sx={{
                        background:
                            "linear-gradient(45deg, #FF6B6B, #4ECDC4, #45B7D1)",
                        backgroundClip: "text",
                        textFillColor: "transparent",
                    }}
                    id="wrapped-header-title" // Needed for some manual tweaking in export
                >
                    {username
                        ? `${username}'s ${year.toString()} Wrapped`
                        : `${year.toString()} Wrapped  `}
                </Typography>
                <Typography variant="subtitle1" color="textSecondary">
                    A year of Bed Wars achievements
                </Typography>
                <Stack direction="row" alignItems="center" gap={1}>
                    {wrappedData?.yearStats &&
                        wrappedData.yearStats.end.queriedAt.getTime() -
                            wrappedData.yearStats.start.queriedAt.getTime() <
                            1000 * 60 * 60 * 24 * 30 * 8 && (
                            <Tooltip
                                title={`The data for this year covers only ~${(
                                    (wrappedData.yearStats.end.queriedAt.getTime() -
                                        wrappedData.yearStats.start.queriedAt.getTime()) /
                                    (1000 * 60 * 60 * 24 * 30)
                                ).toLocaleString(undefined, {
                                    maximumFractionDigits: 1,
                                })} month(s). Statistics may not accurately reflect the entire year.`}
                            >
                                <Warning color="warning" />
                            </Tooltip>
                        )}
                    {dateRangeString && (
                        <Typography variant="caption" color="textSecondary">
                            {dateRangeString}
                        </Typography>
                    )}
                </Stack>
            </Stack>
        </Stack>
    );
}

function RouteComponent() {
    const { uuid: rawUUID } = Route.useParams();
    const uuid = normalizeUUID(rawUUID);
    const { year } = Route.useLoaderDeps();

    const navigate = Route.useNavigate();
    const uuidToUsername = useUUIDToUsername(uuid ? [uuid] : []);
    const username = uuid ? uuidToUsername[uuid] : undefined;
    const { visitPlayer } = usePlayerVisits();

    const { data: wrappedData, isLoading } = useQuery(
        getWrappedQueryOptions({
            uuid: uuid ?? "",
            year,
            timezone: getDefaultTimeZone(),
        }),
    );

    // Export functionality
    const [exportApi, setExportApi] = React.useState<{
        download: () => Promise<void>;
    } | null>(null);

    // Register visits for player on page load
    const [initialUUID] = React.useState(uuid);
    const [initialVisitPlayer] = React.useState(() => visitPlayer);
    React.useEffect(() => {
        if (!initialUUID) return;
        initialVisitPlayer(initialUUID);
    }, [initialVisitPlayer, initialUUID]);

    if (!uuid) {
        return <Navigate to="/wrapped" replace />;
    }

    if (uuid !== rawUUID) {
        return (
            <Navigate
                from="/wrapped/$uuid"
                to="/wrapped/$uuid"
                replace
                params={{ uuid }}
                search={(oldSearch) => oldSearch}
            />
        );
    }

    return (
        <>
            <ConfettiEffect />
            <Stack spacing={3}>
                <meta
                    name="description"
                    content={`View ${username ?? "a player"}&apos;s year in review for ${year.toString()}, showcasing their achievements, milestones, and highlights.`}
                />
                <link
                    rel="canonical"
                    href={`https://prismoverlay.com/wrapped/${uuid}`}
                />
                <UserSearch
                    onSubmit={(uuid) => {
                        visitPlayer(uuid);
                        navigate({
                            params: { uuid },
                            search: (oldSearch) => oldSearch,
                        }).catch((error: unknown) => {
                            captureException(error, {
                                tags: {
                                    param: "uuid",
                                },
                                extra: {
                                    message: "Failed to update search params",
                                    uuid,
                                },
                            });
                        });
                    }}
                />
                <WrappedHeader
                    wrappedData={wrappedData}
                    uuid={uuid}
                    year={year}
                />
                {wrappedData?.yearStats && uuid && (
                    <Box sx={{ display: "flex", justifyContent: "center" }}>
                        <Button
                            variant="contained"
                            startIcon={<Download />}
                            onClick={() => {
                                void exportApi?.download();
                            }}
                            disabled={!exportApi}
                            size="large"
                        >
                            Export Summary
                        </Button>
                    </Box>
                )}
                <WrappedStatsContent
                    wrappedData={wrappedData}
                    isLoading={isLoading}
                />
                {wrappedData?.yearStats && username && (
                    <ExportImageMount
                        onReady={(api) => {
                            setExportApi(api);
                        }}
                        onCapture={(node) => {
                            // Crazy hack: Add some dots to give it some more space as it gets clipped by default
                            // Likely due to font-rendering differences between browser and canvas
                            // https://github.com/bubkoo/html-to-image/issues/132
                            const header = node.querySelector(
                                "#wrapped-header-title",
                            );
                            const suffix = " . . ";
                            if (header && !header.textContent.endsWith(suffix))
                                header.textContent += suffix;
                        }}
                        filename={`${username}-${year.toString()}-wrapped.png`}
                    >
                        <ExportStatsCard
                            uuid={uuid}
                            year={year}
                            wrappedData={{
                                ...wrappedData,
                                yearStats: wrappedData.yearStats,
                            }}
                        />
                    </ExportImageMount>
                )}
                {wrappedData?.year !== undefined && wrappedData.yearStats && (
                    <Card
                        variant="outlined"
                        sx={{
                            background:
                                "linear-gradient(135deg, #a8edea22 0%, #fed6e311 100%)",
                            border: "2px solid #a8edea",
                        }}
                    >
                        <CardContent>
                            <Typography
                                variant="h5"
                                textAlign="center"
                                fontWeight="bold"
                                gutterBottom
                            >
                                🎉 What a Year! 🎉
                            </Typography>
                            <Typography
                                variant="body1"
                                textAlign="center"
                                color="textSecondary"
                            >
                                Thank you for an amazing{" "}
                                {wrappedData.year.toString()}! Here&apos;s to
                                even more victories in the next year.
                            </Typography>
                        </CardContent>
                    </Card>
                )}
            </Stack>
        </>
    );
}
