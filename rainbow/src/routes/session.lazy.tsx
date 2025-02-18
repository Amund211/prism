import { HistoryChart } from "#charts/history/chart.tsx";
import { TimeInterval } from "#intervals.ts";
import { getHistoryQueryOptions } from "#queries/history.ts";
import { computeStat } from "#stats/index.ts";
import {
    ALL_GAMEMODE_KEYS,
    ALL_STAT_KEYS,
    GamemodeKey,
    StatKey,
} from "#stats/keys.ts";
import {
    getFullStatLabel,
    getGamemodeLabel,
    getShortStatLabel,
    getVariantLabel,
} from "#stats/labels.ts";
import { computeStatProgression, StatProgression } from "#stats/progression.ts";
import { TrendingDown, TrendingFlat, TrendingUp } from "@mui/icons-material";
import {
    Card,
    CardContent,
    Grid2 as Grid,
    MenuItem,
    Select,
    Stack,
    SvgIconOwnProps,
    Tooltip,
    Typography,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { createLazyFileRoute, getRouteApi } from "@tanstack/react-router";
import React from "react";

export const Route = createLazyFileRoute("/session")({
    component: RouteComponent,
});

const route = getRouteApi("/session");

interface SessionStatCardProps {
    uuid: string;
    timeInterval: TimeInterval & { type: "day" | "week" | "month" };
    stat: StatKey;
    gamemode: GamemodeKey;
}

const SessionStatCard: React.FC<SessionStatCardProps> = ({
    uuid,
    timeInterval,
    stat,
    gamemode,
}) => {
    const { data } = useQuery(
        getHistoryQueryOptions({
            uuid,
            start: timeInterval.start,
            end: timeInterval.end,
            limit: 2,
        }),
    );

    if (data === undefined || data.length === 0) {
        return "No data";
    }

    if (data.length === 1) {
        return "Not enough data";
    }

    if (data.length > 2) {
        throw new Error("Expected at most 2 data points");
    }

    const [start, end] = data;

    const startDate = start.queriedAt;
    const endDate = end.queriedAt;

    const startValue = computeStat(start, gamemode, stat, "overall", data);
    const endValue = computeStat(end, gamemode, stat, "overall", data);
    const sessionValue = computeStat(end, gamemode, stat, "session", data);

    // Only different than sessionValue for complex stats (e.g. fkdr)
    const diff =
        endValue !== null && startValue !== null ? endValue - startValue : null;

    if (
        startValue === null ||
        endValue === null ||
        diff === null ||
        sessionValue === null
    ) {
        return "Some nulls";
    }

    const intervalTypeName = {
        day: "Daily",
        week: "Weekly",
        month: "Monthly",
    }[timeInterval.type];

    const trendDirection = diff == 0 ? "flat" : diff > 0 ? "up" : "down";

    const badStats: StatKey[] = ["deaths", "finalDeaths", "bedsLost", "losses"];
    // Intentionally not including "index" as the number is usually so large that we don't want decmials. TODO: Could be fixed by better conditional decimal rendering for large numbers.
    const floatStats: StatKey[] = ["fkdr", "kdr", "stars"];

    const shortPrecision = floatStats.includes(stat) ? 2 : 0;
    const shortFormat: Intl.NumberFormatOptions = {
        minimumFractionDigits: shortPrecision,
        maximumFractionDigits: shortPrecision,
    };

    const longPrecision = floatStats.includes(stat) ? 3 : 0;
    const longFormat: Intl.NumberFormatOptions = {
        minimumFractionDigits: longPrecision,
        maximumFractionDigits: longPrecision,
    };

    const trendColor: SvgIconOwnProps["color"] =
        trendDirection === "flat"
            ? undefined
            : (trendDirection === "up") === badStats.includes(stat)
              ? "error"
              : "success";

    return (
        <Card variant="outlined" sx={{ height: "100%" }}>
            <CardContent>
                <Tooltip
                    title={`${startDate.toLocaleString()} → ${endDate.toLocaleString()}`}
                >
                    <Typography variant="subtitle2">
                        {`${intervalTypeName} ${getGamemodeLabel(gamemode)} ${getFullStatLabel(stat)}`}
                    </Typography>
                </Tooltip>
                <Stack
                    direction="row"
                    gap={1}
                    alignItems="center"
                    justifyContent="space-between"
                >
                    <Typography variant="body1">
                        {sessionValue.toLocaleString(undefined, {
                            ...longFormat,
                        })}
                    </Typography>
                    <Tooltip
                        title={`${startValue.toLocaleString(undefined, {
                            ...longFormat,
                        })} → ${endValue.toLocaleString(undefined, {
                            ...longFormat,
                        })}`}
                    >
                        <Stack direction="row" gap={0.5} alignItems="center">
                            <Typography variant="caption" color={trendColor}>
                                {diff.toLocaleString(undefined, {
                                    signDisplay: "always",
                                    ...shortFormat,
                                })}
                            </Typography>
                            {diff > 0 ? (
                                <TrendingUp
                                    color={trendColor}
                                    fontSize="small"
                                />
                            ) : diff < 0 ? (
                                <TrendingDown
                                    color={trendColor}
                                    fontSize="small"
                                />
                            ) : (
                                <TrendingFlat
                                    color={trendColor}
                                    fontSize="small"
                                />
                            )}
                        </Stack>
                    </Tooltip>
                </Stack>
            </CardContent>
        </Card>
    );
};

interface ProgressionValueAndMilestoneProps {
    progression: StatProgression;
}

const ProgressionValueAndMilestone: React.FC<
    ProgressionValueAndMilestoneProps
> = ({ progression }) => {
    const renderValues = (
        currentValue: number,
        nextMilestoneValue: number,
        renderValue: (value: number) => React.ReactNode,
        badStat: boolean,
    ) => {
        const direction =
            nextMilestoneValue > currentValue
                ? "up"
                : nextMilestoneValue < currentValue
                  ? "down"
                  : "flat";

        const color: SvgIconOwnProps["color"] =
            direction === "flat"
                ? undefined
                : (direction === "up") === badStat
                  ? "error"
                  : "success";

        return (
            <Stack direction="row" gap={0.5} alignItems="center">
                {renderValue(currentValue)}
                {direction === "up" ? (
                    <TrendingUp color={color} fontSize="medium" />
                ) : direction === "down" ? (
                    <TrendingDown color={color} fontSize="medium" />
                ) : (
                    <TrendingFlat color={color} fontSize="medium" />
                )}
                {renderValue(nextMilestoneValue)}
            </Stack>
        );
    };
    switch (progression.stat) {
        case "stars":
            // TODO: Format based on prestige colors
            return renderValues(
                progression.currentValue,
                progression.nextMilestoneValue,
                (value) => (
                    <Typography variant="body1">
                        {value.toLocaleString(undefined, {
                            maximumFractionDigits: 2,
                        })}
                    </Typography>
                ),
                false,
            );
        case "fkdr":
        case "kdr":
            return renderValues(
                progression.currentValue,
                progression.nextMilestoneValue,
                (value) => (
                    <Typography variant="body1">
                        {value.toLocaleString(undefined, {
                            maximumFractionDigits: 2,
                        })}
                    </Typography>
                ),
                false,
            );
        case "index":
        case "experience":
        case "winstreak":
        case "gamesPlayed":
        case "wins":
        case "bedsBroken":
        case "finalKills":
        case "kills":
            return renderValues(
                progression.currentValue,
                progression.nextMilestoneValue,
                (value) => (
                    <Typography variant="body1">
                        {value.toLocaleString()}
                    </Typography>
                ),
                false,
            );
        case "losses":
        case "bedsLost":
        case "finalDeaths":
        case "deaths":
            return renderValues(
                progression.currentValue,
                progression.nextMilestoneValue,
                (value) => (
                    <Typography variant="body1">
                        {value.toLocaleString()}
                    </Typography>
                ),
                true,
            );
        default:
            progression satisfies never;
    }
};

interface ProgressionCaptionProps {
    progression: StatProgression;
}

const ProgressionCaption: React.FC<ProgressionCaptionProps> = ({
    progression,
}) => {
    switch (progression.stat) {
        case "stars":
            return (
                <Typography variant="caption">
                    {`${progression.progressPerDay.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${getShortStatLabel(progression.stat)}/day`}
                </Typography>
            );
        case "fkdr":
            return (
                <Typography variant="caption">
                    {`${progression.progressPerDay.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}/day (${progression.sessionQuotient.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} session ${getShortStatLabel("fkdr")}, ${progression.dividendPerDay.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${getShortStatLabel("finalKills")}/day, ${progression.divisorPerDay.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${getShortStatLabel("finalDeaths")}/day)`}
                </Typography>
            );
        case "kdr":
            return (
                <Typography variant="caption">
                    {`${progression.progressPerDay.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}/day (${progression.sessionQuotient.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} session ${getShortStatLabel("kdr")}, ${progression.dividendPerDay.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${getShortStatLabel("kills")}/day, ${progression.divisorPerDay.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${getShortStatLabel("deaths")}/day)`}
                </Typography>
            );
        case "index":
            // TODO
            return <Typography variant="caption">TODO</Typography>;
        case "experience":
        case "winstreak":
        case "gamesPlayed":
        case "wins":
        case "losses":
        case "bedsBroken":
        case "bedsLost":
        case "finalKills":
        case "finalDeaths":
        case "kills":
        case "deaths":
            return (
                <Typography variant="caption">
                    {`${progression.progressPerDay.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${getShortStatLabel(progression.stat)}/day`}
                </Typography>
            );
        default:
            progression satisfies never;
    }
};

interface StatProgressionCardProps {
    uuid: string;
    trackingInterval: TimeInterval;
    stat: StatKey;
    gamemode: GamemodeKey;
}

const StatProgressionCard: React.FC<StatProgressionCardProps> = ({
    uuid,
    trackingInterval,
    stat,
    gamemode,
}) => {
    // History data to calculate stat progression speed
    const { data: trackingHistory } = useQuery(
        getHistoryQueryOptions({
            uuid,
            ...trackingInterval,
            limit: 2,
        }),
    );

    // TODO: Get "current" stats in a better way
    const currentDate = new Date(trackingInterval.end);
    currentDate.setHours(23, 59, 59, 999);
    const { data: currentHistory } = useQuery(
        getHistoryQueryOptions({
            uuid,
            start: trackingInterval.start,
            end: currentDate,
            limit: 2,
        }),
    );
    if (currentHistory === undefined || currentHistory.length === 0) {
        return "No data";
    }
    const currentStats = currentHistory[currentHistory.length - 1];

    const now = new Date();
    const currentDateIsToday =
        now.getFullYear() === currentDate.getFullYear() &&
        now.getMonth() === currentDate.getMonth() &&
        now.getDate() === currentDate.getDate();
    const referenceDate = currentDateIsToday ? now : currentDate;

    const progression = computeStatProgression(
        trackingHistory,
        currentStats,
        stat,
        gamemode,
    );

    if (progression.error) {
        return progression.reason;
    }

    const projectedMilestoneDate = new Date(
        referenceDate.getTime() +
            progression.daysUntilMilestone * 24 * 60 * 60 * 1000,
    );

    return (
        <Card variant="outlined" sx={{ height: "100%" }}>
            <CardContent>
                <Typography variant="subtitle2">
                    {`${getGamemodeLabel(gamemode, true)} ${getFullStatLabel(stat)} milestone progress`}
                </Typography>

                <ProgressionValueAndMilestone progression={progression} />
                <Stack
                    direction="row"
                    gap={1}
                    alignItems="center"
                    justifyContent="space-between"
                >
                    <Typography variant="body1">
                        {Number.isFinite(progression.daysUntilMilestone)
                            ? `Expected to reach: ${projectedMilestoneDate.toLocaleDateString(
                                  undefined,
                                  {
                                      dateStyle: "medium",
                                  },
                              )} (in ${progression.daysUntilMilestone.toFixed(1)} days)`
                            : `Expected to reach: Never (session ${getShortStatLabel(stat)} too ${progression.trendingUpward ? "low" : "high"})`}
                    </Typography>
                    <Tooltip
                        title={`Based on stats from ${progression.trackingDataTimeInterval.start.toLocaleString(undefined, { dateStyle: "medium" })} to ${progression.trackingDataTimeInterval.end.toLocaleString(undefined, { dateStyle: "medium" })}`}
                    >
                        {/* Need a div here for some reason for the tooltip to work :^( */}
                        <div>
                            <ProgressionCaption progression={progression} />
                        </div>
                    </Tooltip>
                </Stack>
            </CardContent>
        </Card>
    );
};
function RouteComponent() {
    const { uuid, gamemode, stat, variantSelection } = route.useSearch();
    const { timeIntervals, trackingInterval } = route.useLoaderDeps();
    const navigate = route.useNavigate();
    const { day, week, month } = timeIntervals;

    const variants =
        variantSelection === "both"
            ? (["session", "overall"] as const)
            : ([variantSelection] as const);

    const cardSize = {
        xs: 6,
        sm: 4,
    };
    const chartSize = {
        xs: 12,
        lg: 6,
    };
    return (
        <Stack spacing={1}>
            <Stack direction="row" gap={1}>
                <Select
                    value={gamemode}
                    label="Gamemode"
                    fullWidth
                    onChange={(event) => {
                        const newGamemode = event.target.value as GamemodeKey;
                        navigate({
                            search: (oldSearch) => ({
                                ...oldSearch,
                                gamemode: newGamemode,
                            }),
                        }).catch((error: unknown) => {
                            // TODO: Handle error
                            console.error(
                                "Failed to update search params: gamemode",
                                error,
                            );
                        });
                    }}
                >
                    {ALL_GAMEMODE_KEYS.map((gamemode) => (
                        <MenuItem key={gamemode} value={gamemode}>
                            {getGamemodeLabel(gamemode, true)}
                        </MenuItem>
                    ))}
                </Select>
                <Select
                    value={stat}
                    label="Stat"
                    fullWidth
                    onChange={(event) => {
                        const newStat = event.target.value as StatKey;
                        navigate({
                            search: (oldSearch) => ({
                                ...oldSearch,
                                stat: newStat,
                            }),
                        }).catch((error: unknown) => {
                            // TODO: Handle error
                            console.error(
                                "Failed to update search params: stat",
                                error,
                            );
                        });
                    }}
                >
                    {ALL_STAT_KEYS.map((stat) => (
                        <MenuItem key={stat} value={stat}>
                            {getFullStatLabel(stat, true)}
                        </MenuItem>
                    ))}
                </Select>
            </Stack>
            <Grid container spacing={1}>
                <Grid size={cardSize}>
                    <SessionStatCard
                        uuid={uuid}
                        timeInterval={{ ...day, type: "day" }}
                        gamemode={gamemode}
                        stat={stat}
                    />
                </Grid>
                <Grid size={cardSize}>
                    <SessionStatCard
                        uuid={uuid}
                        timeInterval={{ ...week, type: "week" }}
                        gamemode={gamemode}
                        stat={stat}
                    />
                </Grid>
                <Grid size={cardSize}>
                    <SessionStatCard
                        uuid={uuid}
                        timeInterval={{ ...month, type: "month" }}
                        gamemode={gamemode}
                        stat={stat}
                    />
                </Grid>
            </Grid>
            <StatProgressionCard
                uuid={uuid}
                trackingInterval={trackingInterval}
                gamemode={gamemode}
                stat={stat}
            />
            <Select
                value={variantSelection}
                label="Variants"
                fullWidth
                onChange={(event) => {
                    const newSelection = event.target.value as
                        | "session"
                        | "overall"
                        | "both";

                    navigate({
                        search: (oldSearch) => ({
                            ...oldSearch,
                            variantSelection: newSelection,
                        }),
                    }).catch((error: unknown) => {
                        // TODO: Handle error
                        console.error(
                            "Failed to update search params: variantSelection",
                            error,
                        );
                    });
                }}
            >
                <MenuItem value="overall">
                    {getVariantLabel("overall", true)}
                </MenuItem>
                <MenuItem value="session">
                    {getVariantLabel("session", true)}
                </MenuItem>
                <MenuItem value="both">Both</MenuItem>
            </Select>
            <Grid container spacing={1}>
                <Grid size={chartSize}>
                    <HistoryChart
                        start={day.start}
                        end={day.end}
                        uuids={[uuid]}
                        gamemodes={[gamemode]}
                        stats={[stat]}
                        variants={variants}
                        limit={100}
                    />
                </Grid>
                <Grid size={chartSize}>
                    <HistoryChart
                        start={week.start}
                        end={week.end}
                        uuids={[uuid]}
                        gamemodes={[gamemode]}
                        stats={[stat]}
                        variants={variants}
                        limit={100}
                    />
                </Grid>
                <Grid size={chartSize}>
                    <HistoryChart
                        start={month.start}
                        end={month.end}
                        uuids={[uuid]}
                        gamemodes={[gamemode]}
                        stats={[stat]}
                        variants={variants}
                        limit={100}
                    />
                </Grid>
            </Grid>
        </Stack>
    );
}
