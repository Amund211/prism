import { queryClient } from "#queryClient.ts";
import { fallback } from "@tanstack/zod-adapter";
import { z } from "zod";
import { getUsernameQueryOptions } from "#queries/username.ts";
import { timeIntervalsFromDefinition } from "#intervals.ts";
import { HistoryChart, SimpleHistoryChart } from "#charts/history/chart.tsx";
import { TimeIntervalPicker } from "#components/TimeIntervalPicker.tsx";
import { UserSearch } from "#components/UserSearch.tsx";
import { ChartSynchronizerProvider } from "#contexts/ChartSynchronizer/provider.tsx";
import { type TimeInterval } from "#intervals.ts";
import { getHistoryQueryOptions } from "#queries/history.ts";
import { getSessionsQueryOptions, type Sessions } from "#queries/sessions.ts";
import { useUUIDToUsername } from "#queries/username.ts";
import { computeStat } from "#stats/index.ts";
import {
    ALL_GAMEMODE_KEYS,
    ALL_STAT_KEYS,
    type GamemodeKey,
    type StatKey,
} from "#stats/keys.ts";
import {
    getFullStatLabel,
    getGamemodeLabel,
    getShortStatLabel,
    getVariantLabel,
} from "#stats/labels.ts";
import {
    computeStatProgression,
    type StatProgression,
} from "#stats/progression.ts";
import {
    Info,
    TrendingDown,
    TrendingFlat,
    TrendingUp,
    InfoOutlined,
    QueryStats,
    Warning,
} from "@mui/icons-material";
import {
    Avatar,
    Box,
    Card,
    CardContent,
    FormControlLabel,
    Grid,
    IconButton,
    MenuItem,
    Select,
    Skeleton,
    Stack,
    type SvgIconOwnProps,
    Switch,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    ToggleButton,
    ToggleButtonGroup,
    Tooltip,
    Typography,
} from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import {
    createFileRoute,
    createLink,
    useNavigate,
} from "@tanstack/react-router";
import React, { type JSX } from "react";
import { usePlayerVisits } from "#contexts/PlayerVisits/hooks.ts";
import { addExtrapolatedSessions } from "#helpers/session.ts";

const sessionSearchSchema = z.object({
    timeIntervalDefinition: fallback(
        z.union([
            z.object({
                type: z.literal("contained"),
                date: fallback(z.coerce.date().optional(), undefined),
            }),
            z.object({
                type: z.literal("until"),
                date: fallback(z.coerce.date().optional(), undefined),
            }),
        ]),
        { type: "contained" },
    ),
    trackingStart: fallback(z.coerce.date().optional(), undefined).transform(
        (value) => {
            if (value === undefined) {
                return new Date(1970, 0, 1);
            }
            return value;
        },
    ),
    gamemode: fallback(z.enum(ALL_GAMEMODE_KEYS), "overall"),
    stat: fallback(z.enum(ALL_STAT_KEYS), "fkdr"),
    variantSelection: fallback(z.enum(["session", "overall", "both"]), "both"),
    sessionTableMode: fallback(z.enum(["total", "rate"]), "total"),
    showExtrapolatedSessions: fallback(z.boolean(), false),
});

export const Route = createFileRoute("/session/$uuid")({
    loaderDeps: ({ search: { timeIntervalDefinition, trackingStart } }) => {
        const timeIntervals = timeIntervalsFromDefinition({
            // If missing -> today's date
            date: new Date(),
            ...timeIntervalDefinition,
        });
        return {
            timeIntervalDefinition,
            trackingInterval: {
                start: trackingStart,
                end: timeIntervals.day.end,
            },
            timeIntervals,
        };
    },
    loader: ({
        params: { uuid },
        deps: { timeIntervals, trackingInterval },
    }) => {
        const { day, week, month } = timeIntervals;
        // TODO: Rate limiting
        Promise.all([
            [day, week, month].map(({ start, end }) =>
                Promise.all([
                    queryClient.fetchQuery(
                        getHistoryQueryOptions({ uuid, start, end, limit: 2 }),
                    ),
                    queryClient.fetchQuery(
                        getHistoryQueryOptions({
                            uuid,
                            start,
                            end,
                            limit: 100,
                        }),
                    ),
                ]),
            ),
            queryClient.fetchQuery(
                getHistoryQueryOptions({
                    uuid,
                    ...trackingInterval,
                    limit: 2,
                }),
            ),
            queryClient.fetchQuery(getUsernameQueryOptions(uuid)),
        ]).catch((e: unknown) => {
            // TODO: Report error
            console.error(e);
        });
    },
    validateSearch: sessionSearchSchema,
    component: RouteComponent,
});

const RouterLinkIconButton = createLink(IconButton);
const RouterLinkToggleButton = createLink(ToggleButton);

interface SessionsProps {
    uuid: string;
    gamemode: GamemodeKey;
    stat: StatKey;
    start: Date;
    end: Date;
    tableMode: "total" | "rate";
    showExtrapolatedSessions: boolean;
}

const renderDuration = (end: Date, start: Date) => {
    const duration = end.getTime() - start.getTime();
    const hours = Math.floor(duration / (1000 * 60 * 60));
    const minutes = Math.floor(
        (duration % (1000 * 60 * 60)) / (1000 * 60),
    ).toLocaleString();

    // Align the hours with the other rows if this row has hours
    const paddedMinutes =
        minutes.length === 1 && hours ? `0${minutes}` : minutes;

    return hours
        ? `${hours.toLocaleString()}h ${paddedMinutes}m`
        : `${paddedMinutes}m`;
};

const isLinearStat = (stat: StatKey) => {
    return !["fkdr", "kdr", "index"].includes(stat);
};

const getRelatedStats = (stat: StatKey): StatKey[] => {
    switch (stat) {
        case "fkdr":
            return ["finalKills", "finalDeaths"];
        case "kdr":
            return ["kills", "deaths"];
        case "index":
            return ["finalKills", "finalDeaths", "stars"];
        default:
            return [];
    }
};

const Sessions: React.FC<SessionsProps> = ({
    uuid,
    gamemode,
    stat,
    start,
    end,
    tableMode,
    showExtrapolatedSessions,
}) => {
    const navigate = useNavigate();

    const { data: history } = useQuery(
        getHistoryQueryOptions({
            uuid,
            start,
            end,
            limit: 2,
        }),
    );

    const { data: flashlightSessions } = useQuery(
        getSessionsQueryOptions({
            uuid,
            start,
            end,
        }),
    );

    const renderHeader = (showExtrapolatedToggle?: JSX.Element) => (
        <Stack
            direction="row"
            gap={1}
            alignItems="center"
            justifyContent="space-between"
        >
            <Stack
                direction="row"
                gap={1}
                alignItems="center"
                justifyContent="space-between"
            >
                <Typography variant="subtitle2">Sessions</Typography>
                <Tooltip title="Sessions are automatically recorded when using the Prism Overlay. Users who have disabled 'Online Game Stats' in the settings, or are not using the Prism Overlay may have weird or missing sessions.">
                    <InfoOutlined fontSize="small" />
                </Tooltip>
            </Stack>
            <Stack direction="row" gap={3} alignItems="center">
                {showExtrapolatedToggle}
                <ToggleButtonGroup
                    exclusive
                    size="small"
                    value={tableMode}
                    aria-label="Session table mode"
                >
                    <RouterLinkToggleButton
                        value="total"
                        from="/session/$uuid"
                        to="/session/$uuid"
                        search={(oldSearch) => ({
                            ...oldSearch,
                            sessionTableMode: "total",
                        })}
                    >
                        Total
                    </RouterLinkToggleButton>
                    <RouterLinkToggleButton
                        value="rate"
                        from="/session/$uuid"
                        to="/session/$uuid"
                        search={(oldSearch) => ({
                            ...oldSearch,
                            sessionTableMode: "rate",
                        })}
                    >
                        Rate (/hour)
                    </RouterLinkToggleButton>
                </ToggleButtonGroup>
            </Stack>
        </Stack>
    );

    if (flashlightSessions === undefined) {
        return (
            <Card
                variant="outlined"
                sx={{ height: "100%", flexGrow: 1, overflow: "scroll" }}
            >
                <CardContent>
                    {renderHeader()}
                    <Skeleton variant="rounded" height={120} sx={{ mt: 2 }} />
                </CardContent>
            </Card>
        );
    }

    const allSessions = addExtrapolatedSessions(flashlightSessions, history);
    const sessions = showExtrapolatedSessions
        ? allSessions
        : allSessions.filter((session) => !session.extrapolated);

    if (sessions.length === 0) {
        return (
            <Card
                variant="outlined"
                sx={{ height: "100%", flexGrow: 1, overflow: "scroll" }}
            >
                <CardContent>
                    {renderHeader()}
                    <Stack direction="row" gap={0.5} alignItems="center">
                        <Info color="error" fontSize="small" />
                        <Typography variant="body1">
                            No sessions found
                        </Typography>
                    </Stack>
                </CardContent>
            </Card>
        );
    }

    const labelSuffix = tableMode === "rate" ? "/hour" : "";

    const statAlreadyIncluded = (stat: StatKey) =>
        ["gamesPlayed", "wins"].includes(stat);

    const hasExtrapolatedSessions = allSessions.some(
        (session) => session.extrapolated,
    );
    const willShowExtrapolatedSessions =
        hasExtrapolatedSessions && showExtrapolatedSessions;
    const hasNonConsecutiveSessions = sessions.some(
        (session) => !session.consecutive,
    );

    return (
        <Card
            variant="outlined"
            sx={{ height: "100%", flexGrow: 1, overflow: "scroll" }}
        >
            <CardContent>
                <Stack gap={1}>
                    {renderHeader(
                        hasExtrapolatedSessions ? (
                            <FormControlLabel
                                control={
                                    <Switch
                                        checked={showExtrapolatedSessions}
                                        onChange={(_, checked) => {
                                            navigate({
                                                from: "/session/$uuid",
                                                to: "/session/$uuid",
                                                search: (oldSearch) => ({
                                                    ...oldSearch,
                                                    showExtrapolatedSessions:
                                                        checked,
                                                }),
                                            }).catch((error: unknown) => {
                                                // TODO: Handle error
                                                console.error(
                                                    "Failed to update search params: showExtrapolatedSessions",
                                                    error,
                                                );
                                            });
                                        }}
                                    />
                                }
                                label={
                                    <Stack
                                        direction="row"
                                        gap={1}
                                        alignItems="center"
                                    >
                                        <Typography
                                            variant="body2"
                                            color="textSecondary"
                                        >
                                            Show extrapolated sessions
                                        </Typography>
                                        <Tooltip title="Show the player's stats between sessions recorded by the Prism Overlay. These sessions may include stats from multiple sessions, and the duration may be incorrect.">
                                            <InfoOutlined fontSize="small" />
                                        </Tooltip>
                                    </Stack>
                                }
                                labelPlacement="start"
                            />
                        ) : undefined,
                    )}
                    <TableContainer>
                        <Table>
                            <TableHead>
                                <TableRow>
                                    {(willShowExtrapolatedSessions ||
                                        hasNonConsecutiveSessions) && (
                                        // Cell for extrapolated/non-consecutive info icons
                                        <TableCell
                                            style={{
                                                width: 20,
                                            }}
                                        />
                                    )}
                                    <TableCell>
                                        <Typography variant="subtitle2">
                                            Start
                                        </Typography>
                                    </TableCell>
                                    <TableCell align="right">
                                        <Typography variant="subtitle2">
                                            Duration
                                        </Typography>
                                    </TableCell>
                                    <TableCell align="right">
                                        <Typography variant="subtitle2">
                                            {`${getShortStatLabel(
                                                "gamesPlayed",
                                                true,
                                            )}${labelSuffix}`}
                                        </Typography>
                                    </TableCell>
                                    <TableCell align="right">
                                        <Typography variant="subtitle2">
                                            {`${getShortStatLabel("wins", true)}${labelSuffix}`}
                                        </Typography>
                                    </TableCell>
                                    {!statAlreadyIncluded(stat) && (
                                        <TableCell align="right">
                                            <Typography variant="subtitle2">
                                                {`${getShortStatLabel(stat, true)}${isLinearStat(stat) ? labelSuffix : ""}`}
                                            </Typography>
                                        </TableCell>
                                    )}
                                    {getRelatedStats(stat)
                                        .filter(
                                            (relatedStat) =>
                                                !statAlreadyIncluded(
                                                    relatedStat,
                                                ),
                                        )
                                        .map((relatedStat) => (
                                            <TableCell
                                                align="right"
                                                key={relatedStat}
                                            >
                                                <Typography variant="subtitle2">
                                                    {`${getShortStatLabel(relatedStat, true)}${isLinearStat(relatedStat) ? labelSuffix : ""}`}
                                                </Typography>
                                            </TableCell>
                                        ))}
                                </TableRow>
                            </TableHead>
                            <TableBody>
                                {sessions
                                    .map((session) => {
                                        const durationHours =
                                            (session.end.queriedAt.getTime() -
                                                session.start.queriedAt.getTime()) /
                                            1000 /
                                            60 /
                                            60;

                                        if (durationHours <= 0) {
                                            // This should not happen
                                            // TODO: Report error
                                            return null;
                                        }

                                        const renderStat = (stat: StatKey) => {
                                            const value = computeStat(
                                                session.end,
                                                gamemode,
                                                stat,
                                                "session",
                                                [session.start, session.end],
                                            );
                                            if (value === null) {
                                                return "N/A";
                                            }

                                            if (
                                                tableMode === "rate" &&
                                                isLinearStat(stat)
                                            ) {
                                                const formattedNumber = (
                                                    value / durationHours
                                                ).toLocaleString(undefined, {
                                                    minimumFractionDigits: 2,
                                                    maximumFractionDigits: 2,
                                                });
                                                if (session.extrapolated) {
                                                    return `> ${formattedNumber}`;
                                                }
                                                return formattedNumber;
                                            }

                                            return value.toLocaleString(/*TODO: format based on stat type*/);
                                        };

                                        return (
                                            <TableRow
                                                key={session.start.queriedAt.toString()}
                                            >
                                                {(willShowExtrapolatedSessions ||
                                                    hasNonConsecutiveSessions) && (
                                                    // Cell for extrapolated/non-consecutive info icons
                                                    <TableCell
                                                        style={{
                                                            width: 20,
                                                        }}
                                                        align="center"
                                                    >
                                                        {session.extrapolated && (
                                                            <Tooltip title="The Prism Overlay has not recorded the player's stats during this time. This may be due to the player not using the Prism Overlay; therefore the duration may be incorrect, and the session may include stats from multiple sessions.">
                                                                <InfoOutlined fontSize="small" />
                                                            </Tooltip>
                                                        )}
                                                        {!session.consecutive &&
                                                            !session.extrapolated && (
                                                                <Tooltip
                                                                    title={`The Prism Overlay has not recorded the result of every game during this time. This may be due to the player not using the Prism Overlay or having disabled "Online Game Stats" in their Hypixel settings; therefore the duration may be incorrect, and the session may include stats from multiple sessions.`}
                                                                >
                                                                    <Warning
                                                                        color="warning"
                                                                        fontSize="small"
                                                                    />
                                                                </Tooltip>
                                                            )}
                                                    </TableCell>
                                                )}
                                                <TableCell>
                                                    <Typography variant="body1">
                                                        {session.start.queriedAt.toLocaleString(
                                                            undefined,
                                                            {
                                                                day: "2-digit",
                                                                month: "short",
                                                                year: "numeric",
                                                                hour: "2-digit",
                                                                minute: "2-digit",
                                                            },
                                                        )}
                                                    </Typography>
                                                </TableCell>
                                                <TableCell align="right">
                                                    <Typography variant="body1">
                                                        {session.extrapolated
                                                            ? "< "
                                                            : undefined}
                                                        {renderDuration(
                                                            session.end
                                                                .queriedAt,
                                                            session.start
                                                                .queriedAt,
                                                        )}
                                                    </Typography>
                                                </TableCell>
                                                <TableCell align="right">
                                                    <Typography variant="body1">
                                                        {renderStat(
                                                            "gamesPlayed",
                                                        )}
                                                    </Typography>
                                                </TableCell>
                                                <TableCell align="right">
                                                    <Typography variant="body1">
                                                        {renderStat("wins")}
                                                    </Typography>
                                                </TableCell>
                                                {!statAlreadyIncluded(stat) && (
                                                    <TableCell align="right">
                                                        <Typography variant="body1">
                                                            {renderStat(stat)}
                                                        </Typography>
                                                    </TableCell>
                                                )}
                                                {getRelatedStats(stat)
                                                    .filter(
                                                        (relatedStat) =>
                                                            !statAlreadyIncluded(
                                                                relatedStat,
                                                            ),
                                                    )
                                                    .map((relatedStat) => (
                                                        <TableCell
                                                            align="right"
                                                            key={relatedStat}
                                                        >
                                                            <Typography variant="body1">
                                                                {renderStat(
                                                                    relatedStat,
                                                                )}
                                                            </Typography>
                                                        </TableCell>
                                                    ))}
                                            </TableRow>
                                        );
                                    })
                                    .reverse()}
                            </TableBody>
                        </Table>
                    </TableContainer>
                </Stack>
            </CardContent>
        </Card>
    );
};

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
    const { data: queryData } = useQuery(
        getHistoryQueryOptions({
            uuid,
            start: timeInterval.start,
            end: timeInterval.end,
            limit: 2,
        }),
    );

    const intervalTypeName = {
        day: "Daily",
        week: "Weekly",
        month: "Monthly",
    }[timeInterval.type];

    const cardTitle = (
        <Stack
            direction="row"
            gap={0.5}
            alignItems="center"
            justifyContent="space-between"
        >
            <Typography variant="subtitle2">
                {`${intervalTypeName} ${getGamemodeLabel(gamemode)} ${getFullStatLabel(stat)}`}
            </Typography>
            <Tooltip
                title={`Time interval: ${timeInterval.start.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })} → ${timeInterval.end.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}`}
            >
                <InfoOutlined fontSize="small" />
            </Tooltip>
        </Stack>
    );

    if (queryData === undefined) {
        return (
            <Card variant="outlined" sx={{ height: "100%", flexGrow: 1 }}>
                <CardContent
                    sx={{
                        height: "100%",
                        padding: 2,
                        "&:last-child": { pb: 2 },
                    }}
                >
                    <Stack gap={1} justifyContent="space-between" height="100%">
                        {cardTitle}
                        <Stack>
                            <Stack
                                direction="row"
                                gap={1}
                                alignItems="center"
                                justifyContent="space-between"
                            >
                                <Typography variant="body1">
                                    <Skeleton variant="text" width={50} />
                                </Typography>
                                <Tooltip title={<Skeleton variant="text" />}>
                                    <Stack
                                        direction="row"
                                        gap={0.5}
                                        alignItems="center"
                                    >
                                        <Typography
                                            variant="caption"
                                            color={undefined}
                                        >
                                            <Skeleton
                                                variant="text"
                                                width={30}
                                            />
                                        </Typography>
                                        <TrendingFlat
                                            color={undefined}
                                            fontSize="small"
                                        />
                                    </Stack>
                                </Tooltip>
                            </Stack>
                            <SimpleHistoryChart
                                start={timeInterval.start}
                                end={timeInterval.end}
                                uuid={uuid}
                                gamemode={gamemode}
                                stat={stat}
                                variant="session"
                                limit={100}
                            />
                        </Stack>
                    </Stack>
                </CardContent>
            </Card>
        );
    }

    if (queryData.length === 0) {
        return (
            <Card variant="outlined" sx={{ height: "100%", flexGrow: 1 }}>
                <CardContent
                    sx={{
                        height: "100%",
                        padding: 2,
                        "&:last-child": { pb: 2 },
                    }}
                >
                    <Stack gap={1} justifyContent="space-between" height="100%">
                        {cardTitle}
                        <Stack>
                            <Stack
                                direction="row"
                                gap={0.5}
                                alignItems="center"
                            >
                                <Tooltip title="The player has not recorded any stats with the Prism Overlay in the given time interval. They have either not played, or played without using the Prism Overlay.">
                                    <Info color="error" fontSize="small" />
                                </Tooltip>
                                <Typography variant="body1">
                                    No data found
                                </Typography>
                            </Stack>
                            <SimpleHistoryChart
                                start={timeInterval.start}
                                end={timeInterval.end}
                                uuid={uuid}
                                gamemode={gamemode}
                                stat={stat}
                                variant="session"
                                limit={100}
                            />
                        </Stack>
                    </Stack>
                </CardContent>
            </Card>
        );
    }

    let data = queryData;
    if (data.length === 1) {
        // Hack to show data in the same way as when there are two data points
        data = [data[0], data[0]];
    }

    if (data.length > 2) {
        throw new Error("Expected at most 2 data points");
    }

    const [start, end] = data;

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
        return `Hypixel API disabled for ${getFullStatLabel(stat)}.`;
    }

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
        <Card variant="outlined" sx={{ height: "100%", flexGrow: 1 }}>
            <CardContent
                sx={{ height: "100%", padding: 2, "&:last-child": { pb: 2 } }}
            >
                <Stack gap={1} justifyContent="space-between" height="100%">
                    {cardTitle}
                    <Stack>
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
                                <Stack
                                    direction="row"
                                    gap={0.5}
                                    alignItems="center"
                                >
                                    <Typography
                                        variant="caption"
                                        color={trendColor}
                                    >
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
                        <SimpleHistoryChart
                            start={timeInterval.start}
                            end={timeInterval.end}
                            uuid={uuid}
                            gamemode={gamemode}
                            stat={stat}
                            variant="session"
                            limit={100}
                        />
                    </Stack>
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
        // TODO: Join all quotient cases by returning the dividend and divisor stat names
        case "fkdr":
            return (
                <Typography variant="caption">
                    {`${progression.progressPerDay.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}/day (${progression.sessionQuotient.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} long-time ${getShortStatLabel("fkdr")}, ${progression.dividendPerDay.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${getShortStatLabel("finalKills")}/day, ${progression.divisorPerDay.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${getShortStatLabel("finalDeaths")}/day)`}
                </Typography>
            );
        case "kdr":
            return (
                <Typography variant="caption">
                    {`${progression.progressPerDay.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}/day (${progression.sessionQuotient.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} long-time ${getShortStatLabel("kdr")}, ${progression.dividendPerDay.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${getShortStatLabel("kills")}/day, ${progression.divisorPerDay.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${getShortStatLabel("deaths")}/day)`}
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

const formatDays = (days: number): string => {
    if (days < 1) {
        const hours = Math.round(days * 24);
        if (hours < 1) {
            return "<1 hour";
        }
        const plural = hours !== 1 ? "s" : "";
        return `${Math.round(days * 24).toString()} hour${plural}`;
    }
    if (days < 30) {
        const plural = days !== 1 ? "s" : "";
        return `${Math.round(days).toString()} day${plural}`;
    }
    if (days < 365) {
        const months = Math.round(days / 30);
        const plural = months !== 1 ? "s" : "";
        return `${months.toString()} month${plural}`;
    }

    const years = Math.round(days / 365);
    const plural = years !== 1 ? "s" : "";
    return `${years.toString()} year${plural}`;
};

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

    if (stat === "winstreak") {
        return null;
    }

    if (trackingHistory === undefined || trackingHistory.length === 0) {
        return "No data";
    }
    const currentStats = trackingHistory[trackingHistory.length - 1];

    const currentDate = trackingInterval.end;
    const now = new Date();

    const currentDateIsToday =
        now.getFullYear() === currentDate.getFullYear() &&
        now.getMonth() === currentDate.getMonth() &&
        now.getDate() === currentDate.getDate();
    const referenceDate = currentDateIsToday ? now : currentDate;

    const progression = computeStatProgression(
        trackingHistory,
        trackingInterval.end,
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

    const daysUntilMilestoneFromNow =
        (projectedMilestoneDate.getTime() - now.getTime()) /
        (1000 * 60 * 60 * 24);

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
                              )} (${daysUntilMilestoneFromNow >= 0 ? "in " : ""}${formatDays(Math.abs(daysUntilMilestoneFromNow))}${daysUntilMilestoneFromNow < 0 ? " ago" : ""})`
                            : `Expected to reach: Never (long-time ${getShortStatLabel(stat)} too ${progression.trendingUpward ? "low" : "high"})`}
                    </Typography>

                    <Stack
                        direction="row"
                        gap={0.5}
                        alignItems="center"
                        justifyContent="space-between"
                    >
                        <ProgressionCaption progression={progression} />
                        <Tooltip
                            title={`Based on stats from ${progression.trackingDataTimeInterval.start.toLocaleString(undefined, { dateStyle: "medium" })} to ${progression.trackingDataTimeInterval.end.toLocaleString(undefined, { dateStyle: "medium" })}`}
                        >
                            <InfoOutlined fontSize="small" />
                        </Tooltip>
                    </Stack>
                </Stack>
            </CardContent>
        </Card>
    );
};

function RouteComponent() {
    const { uuid } = Route.useParams();
    const {
        gamemode,
        stat,
        variantSelection,
        sessionTableMode,
        showExtrapolatedSessions,
    } = Route.useSearch();
    const {
        timeIntervalDefinition,
        timeIntervals: { day, week, month },
        trackingInterval,
    } = Route.useLoaderDeps();
    const navigate = Route.useNavigate();
    const username = useUUIDToUsername([uuid])[uuid];
    const { visitPlayer } = usePlayerVisits();

    // Register visits for player on page load
    const [initialUUID] = React.useState(uuid);
    const [initialVisitPlayer] = React.useState(() => visitPlayer);
    React.useEffect(() => {
        initialVisitPlayer(initialUUID);
    }, [initialVisitPlayer, initialUUID]);

    const variants =
        variantSelection === "both"
            ? (["session", "overall"] as const)
            : ([variantSelection] as const);

    const cardSize = {
        xs: 6,
        sm: 4,
    };

    // Stats where we want to show the session value AND the all-time value
    // These are stats where the session and all-time values are usually close
    const statsWhereSessionIsCloseToAllTime: StatKey[] = ["fkdr", "kdr"];

    return (
        <Stack spacing={1}>
            <meta
                name="description"
                content={`View ${username ?? "a player"}'s session stats, including daily, weekly, and monthly stats, as well as a progression towards stat milestones, and individual session breakdowns.`}
            />
            <link
                rel="canonical"
                href={`https://prismoverlay.com/session/${uuid}`}
            />
            <UserSearch
                onSubmit={(uuid) => {
                    visitPlayer(uuid);
                    navigate({
                        params: { uuid },
                        search: (oldSearch) => oldSearch,
                    }).catch((error: unknown) => {
                        // TODO: Handle error
                        console.error(
                            "Failed to update search params: uuid",
                            error,
                        );
                    });
                }}
            />
            <Stack
                direction="row"
                gap={1}
                alignItems="center"
                justifyContent="space-between"
            >
                {/*TODO: Profile picture*/}

                <Stack direction="row" alignItems="center" gap={1}>
                    <Avatar
                        key={uuid}
                        alt={`Profile picture for ${username ?? "unknown"}`}
                        // TODO: Attribution - https://crafatar.com/#meta-attribution
                        src={`https://crafatar.com/avatars/${uuid}?overlay`}
                        variant="square"
                    />
                    {username === undefined ? (
                        <Stack direction="row" alignItems="center">
                            <Skeleton variant="rounded" width={60} />
                            <Typography variant="h6">
                                {"'s session stats"}
                            </Typography>
                        </Stack>
                    ) : (
                        <Typography variant="h6">{`${username}'s session stats`}</Typography>
                    )}
                </Stack>
                <TimeIntervalPicker
                    intervalDefinition={timeIntervalDefinition}
                    onIntervalChange={(newInterval) => {
                        navigate({
                            search: (oldSearch) => ({
                                ...oldSearch,
                                timeIntervalDefinition: newInterval,
                            }),
                        }).catch((error: unknown) => {
                            // TODO: Handle error
                            console.error(
                                "Failed to update search params: timeIntervalDefinition",
                                error,
                            );
                        });
                    }}
                />
            </Stack>
            <Stack direction="row" gap={1}>
                <Select
                    value={gamemode}
                    label="Gamemode"
                    aria-label="Gamemode"
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
                    aria-label="Stat"
                    fullWidth
                    onChange={(event) => {
                        const newStat = event.target.value as StatKey;
                        navigate({
                            search: (oldSearch) => ({
                                ...oldSearch,
                                stat: newStat,
                                variantSelection:
                                    statsWhereSessionIsCloseToAllTime.includes(
                                        newStat,
                                    )
                                        ? "both"
                                        : "session",
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
            <ChartSynchronizerProvider
                queryKey={`${uuid}-${JSON.stringify({ day, week, month })}-${gamemode}-${stat}`}
            >
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
            </ChartSynchronizerProvider>
            <StatProgressionCard
                uuid={uuid}
                trackingInterval={trackingInterval}
                gamemode={gamemode}
                stat={stat}
            />
            <Box>
                <Sessions
                    uuid={uuid}
                    gamemode={gamemode}
                    stat={stat}
                    start={month.start}
                    end={month.end}
                    tableMode={sessionTableMode}
                    showExtrapolatedSessions={showExtrapolatedSessions}
                />
            </Box>
            <Box>
                <Card variant="outlined">
                    <CardContent>
                        <Stack
                            direction="row"
                            gap={1}
                            alignItems="center"
                            justifyContent="space-between"
                        >
                            <Stack direction="row" gap={1} alignItems="center">
                                {username === undefined ? (
                                    <Stack direction="row" alignItems="center">
                                        <Skeleton
                                            variant="rounded"
                                            width={100}
                                        />
                                        <Typography variant="subtitle2">
                                            {`'s ${getFullStatLabel(stat)}`}
                                        </Typography>
                                    </Stack>
                                ) : (
                                    <Typography variant="subtitle2">{`${username}'s ${getFullStatLabel(stat)}`}</Typography>
                                )}
                                <Tooltip title="Show in history explorer">
                                    <RouterLinkIconButton
                                        size="small"
                                        color="primary"
                                        to="/history/explore"
                                        search={{
                                            uuids: [uuid],
                                            gamemodes: [gamemode],
                                            stats: [stat],
                                            variantSelection,
                                            start: month.start,
                                            end: month.end,
                                            limit: 100,
                                        }}
                                    >
                                        <QueryStats />
                                    </RouterLinkIconButton>
                                </Tooltip>
                            </Stack>
                            <ToggleButtonGroup
                                exclusive
                                size="small"
                                value={variantSelection}
                                aria-label="Stat chart variant selection"
                            >
                                <RouterLinkToggleButton
                                    value="overall"
                                    from="/session/$uuid"
                                    to="/session/$uuid"
                                    search={(oldSearch) => ({
                                        ...oldSearch,
                                        variantSelection: "overall",
                                    })}
                                    sx={{ textAlign: "center" }}
                                >
                                    {getVariantLabel("overall", true)}
                                </RouterLinkToggleButton>
                                <RouterLinkToggleButton
                                    value="session"
                                    from="/session/$uuid"
                                    to="/session/$uuid"
                                    search={(oldSearch) => ({
                                        ...oldSearch,
                                        variantSelection: "session",
                                    })}
                                    sx={{ textAlign: "center" }}
                                >
                                    {getVariantLabel("session", true)}
                                </RouterLinkToggleButton>
                                <RouterLinkToggleButton
                                    value="both"
                                    from="/session/$uuid"
                                    to="/session/$uuid"
                                    search={(oldSearch) => ({
                                        ...oldSearch,
                                        variantSelection: "both",
                                    })}
                                    sx={{ textAlign: "center" }}
                                >
                                    Both
                                </RouterLinkToggleButton>
                            </ToggleButtonGroup>
                        </Stack>
                        <Stack
                            padding={1}
                            height={{ xs: 300, sm: 400, md: 500, xl: 600 }}
                        >
                            <HistoryChart
                                start={month.start}
                                end={month.end}
                                uuids={[uuid]}
                                gamemodes={[gamemode]}
                                stats={[stat]}
                                variants={variants}
                                limit={100}
                            />
                        </Stack>
                    </CardContent>
                </Card>
            </Box>
        </Stack>
    );
}
