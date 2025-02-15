import { HistoryChart } from "#charts/history/chart.tsx";
import { getTimeIntervals, TimeInterval } from "#intervals.ts";
import { getHistoryQueryOptions } from "#queries/history.ts";
import { computeStat } from "#stats/index.ts";
import {
    ALL_GAMEMODE_KEYS,
    ALL_STAT_KEYS,
    GamemodeKey,
    StatKey,
    VariantKey,
} from "#stats/keys.ts";
import { TrendingDown, TrendingUp } from "@mui/icons-material";
import {
    Card,
    CardContent,
    Grid2 as Grid,
    MenuItem,
    Select,
    Stack,
    Tooltip,
    Typography,
    TypographyProps,
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

    const trendColor: TypographyProps["color"] =
        trendDirection === "flat"
            ? "text.primary"
            : (trendDirection === "up") === badStats.includes(stat)
              ? "error.main"
              : "success.main";

    return (
        <Card variant="outlined" sx={{ height: "100%" }}>
            <CardContent>
                <Tooltip
                    title={`${startDate.toLocaleString()} → ${endDate.toLocaleString()}`}
                >
                    <Typography variant="subtitle2">
                        {intervalTypeName} {gamemode} {stat}
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
                            {diff < 0 ? (
                                <Typography
                                    variant="caption"
                                    color={trendColor}
                                >
                                    <TrendingDown fontSize="small" />
                                </Typography>
                            ) : (
                                <Typography
                                    variant="caption"
                                    color={trendColor}
                                >
                                    <TrendingUp fontSize="small" />
                                </Typography>
                            )}
                        </Stack>
                    </Tooltip>
                </Stack>
            </CardContent>
        </Card>
    );
};

function RouteComponent() {
    const { uuid, timeInterval } = route.useSearch();
    const { day, week, month } = getTimeIntervals(timeInterval);
    // TODO: URL params
    const [gamemode, setGamemode] = React.useState<GamemodeKey>("overall");
    const [stat, setStat] = React.useState<StatKey>("fkdr");
    const [variants, setVariants] = React.useState<VariantKey[]>([
        "session",
        "overall",
    ]);
    const variantSelection = variants.length === 1 ? variants[0] : "both";

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
                        setGamemode(newGamemode);
                    }}
                >
                    {ALL_GAMEMODE_KEYS.map((gamemode) => (
                        <MenuItem key={gamemode} value={gamemode}>
                            {gamemode}
                        </MenuItem>
                    ))}
                </Select>
                <Select
                    value={stat}
                    label="Stat"
                    fullWidth
                    onChange={(event) => {
                        const newStat = event.target.value as StatKey;
                        setStat(newStat);
                    }}
                >
                    {ALL_STAT_KEYS.map((stat) => (
                        <MenuItem key={stat} value={stat}>
                            {stat}
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
            <Select
                value={variantSelection}
                label="Variants"
                fullWidth
                onChange={(event) => {
                    const newSelection = event.target.value as
                        | "session"
                        | "overall"
                        | "both";
                    switch (newSelection) {
                        case "session":
                            setVariants(["session"]);
                            break;
                        case "overall":
                            setVariants(["overall"]);
                            break;
                        case "both":
                            setVariants(["session", "overall"]);
                            break;
                    }
                }}
            >
                <MenuItem value="overall">Overall</MenuItem>
                <MenuItem value="session">Session</MenuItem>
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
