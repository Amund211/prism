import { getTimeIntervals, TimeInterval } from "#intervals.ts";
import { getHistoryQueryOptions } from "#queries/history.ts";
import { computeStat } from "#stats/index.ts";
import { GamemodeKey, StatKey } from "#stats/keys.ts";
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

    // Only different thatn sessionValue for complex stats (e.g. fkdr)
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
    const floatStats: StatKey[] = ["fkdr", "kdr"];

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
    const stat = "fkdr";

    const cardSize = {
        xs: 6,
        sm: 4,
    };
    return (
        <Stack spacing={1}>
            <Select
                value={gamemode}
                label="Gamemode"
                onChange={(event) => {
                    const newGamemode = event.target.value as GamemodeKey;
                    setGamemode(newGamemode);
                }}
            >
                <MenuItem value="overall">Overall</MenuItem>
                <MenuItem value="solo">Solo</MenuItem>
                <MenuItem value="doubles">Doubles</MenuItem>
                <MenuItem value="threes">Threes</MenuItem>
                <MenuItem value="fours">Fours</MenuItem>
            </Select>
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
        </Stack>
    );
}
