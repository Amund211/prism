import { createFileRoute, createLink } from "@tanstack/react-router";
import { queryClient } from "#queryClient.ts";
import { getHistoryQueryOptions } from "#queries/history.ts";
import { fallback } from "@tanstack/zod-adapter";
import { z } from "zod";
import { getUsernameQueryOptions } from "#queries/username.ts";
import { HistoryChart, HistoryChartTitle } from "#charts/history/chart.tsx";
import { UserMultiSelect } from "#components/UserSearch.tsx";
import {
    ALL_GAMEMODE_KEYS,
    ALL_STAT_KEYS,
    type GamemodeKey,
    type StatKey,
} from "#stats/keys.ts";
import {
    getFullStatLabel,
    getGamemodeLabel,
    getVariantLabel,
} from "#stats/labels.ts";
import { DateTimePicker } from "@mui/x-date-pickers";
import {
    Chip,
    IconButton,
    MenuItem,
    Select,
    Stack,
    ToggleButton,
    ToggleButtonGroup,
    Tooltip,
} from "@mui/material";
import dayjs from "dayjs";
import {
    endOfDay,
    endOfLastDay,
    endOfLastMonth,
    endOfLastWeek,
    endOfLastYear,
    endOfMonth,
    endOfWeek,
    endOfYear,
    startOfDay,
    startOfLastDay,
    startOfLastMonth,
    startOfLastWeek,
    startOfLastYear,
    startOfMonth,
    startOfWeek,
    startOfYear,
} from "#intervals.ts";
import { QueryStats } from "@mui/icons-material";
import { visitPlayer } from "#hooks/useFavoritePlayers.ts";
import React from "react";

const defaultStart = new Date();
defaultStart.setHours(0, 0, 0, 0);
const defaultEnd = new Date();
defaultEnd.setHours(23, 59, 59, 999);

const historyExploreSearchSchema = z.object({
    // TODO: Read "preferred user" from local storage or similar
    uuids: fallback(z.array(z.string()).readonly(), []),
    start: fallback(z.coerce.date(), defaultStart),
    end: fallback(z.coerce.date(), defaultEnd),
    limit: fallback(z.number().int().min(1).max(50), 50),
    stats: fallback(z.enum(ALL_STAT_KEYS).array().readonly(), ["fkdr"]),
    gamemodes: fallback(z.enum(ALL_GAMEMODE_KEYS).array().readonly(), [
        "overall",
    ]),
    variantSelection: fallback(
        z.enum(["session", "overall", "both"]),
        "session",
    ),
});

export const Route = createFileRoute("/history/explore")({
    loaderDeps: ({ search: { uuids, start, end, limit } }) => ({
        uuids,
        start,
        end,
        limit,
    }),

    loader: ({ deps: { uuids, start, end, limit } }) => {
        // TODO: Rate limiting
        Promise.all([
            ...uuids.map((uuid) =>
                queryClient.fetchQuery(
                    getHistoryQueryOptions({ uuid, start, end, limit }),
                ),
            ),
            ...uuids.map((uuid) =>
                queryClient.fetchQuery(getUsernameQueryOptions(uuid)),
            ),
        ]).catch((e: unknown) => {
            // TODO: Report error
            console.error(e);
        });
    },
    validateSearch: historyExploreSearchSchema,
    component: Index,
});

const RouterLinkChip = createLink(Chip);
const RouterLinkIconButton = createLink(IconButton);
const RouterLinkToggleButton = createLink(ToggleButton);

function Index() {
    const { uuids, stats, gamemodes, variantSelection, start, end, limit } =
        Route.useSearch();
    const navigate = Route.useNavigate();

    // Register visits for all players on page load
    const [initialUUIDs] = React.useState(uuids);
    React.useEffect(() => {
        initialUUIDs.forEach((uuid) => {
            visitPlayer(uuid);
        });
    }, [initialUUIDs]);

    const variants =
        variantSelection === "both"
            ? (["session", "overall"] as const)
            : ([variantSelection] as const);

    const now = new Date();
    const timeFilterOptions = [
        {
            label: "Today",
            start: startOfDay(now),
            end: endOfDay(now),
        },
        {
            label: "Yesterday",
            start: startOfLastDay(now),
            end: endOfLastDay(now),
        },
        {
            label: "This week",
            start: startOfWeek(now),
            end: endOfWeek(now),
        },
        {
            label: "Last week",
            start: startOfLastWeek(now),
            end: endOfLastWeek(now),
        },
        {
            label: "This month",
            start: startOfMonth(now),
            end: endOfMonth(now),
        },
        {
            label: "Last month",
            start: startOfLastMonth(now),
            end: endOfLastMonth(now),
        },
        {
            label: "This year",
            start: startOfYear(now),
            end: endOfYear(now),
        },
        {
            label: "Last year",
            start: startOfLastYear(now),
            end: endOfLastYear(now),
        },
    ];

    const badSelectionCount: string[] = [];
    if (uuids.length !== 1) {
        badSelectionCount.push("user");
    }
    if (stats.length !== 1) {
        badSelectionCount.push("statistic");
    }
    if (gamemodes.length !== 1) {
        badSelectionCount.push("gamemode");
    }

    const canGoToSessionPage = badSelectionCount.length === 0;

    let badSelectionCountString = "";
    switch (badSelectionCount.length) {
        case 0:
            break;
        case 1:
            badSelectionCountString = badSelectionCount[0];
            break;
        case 2:
            badSelectionCountString = `${badSelectionCount[0]} and ${badSelectionCount[1]}`;
            break;
        default:
            badSelectionCountString = `${badSelectionCount.slice(0, -1).join(", ")}, and ${badSelectionCount[badSelectionCount.length - 1]}`;
    }

    const goToSessionPageTooltip = canGoToSessionPage
        ? "Show in session page"
        : `Select a single ${
              badSelectionCountString
          } to enable showing in session page.`;

    const endOfToday = endOfDay(now);
    const sessionPageEndDate =
        end.getTime() > endOfToday.getTime() ? endOfToday : end;

    return (
        <Stack gap={1} height="100%">
            <meta
                name="description"
                content="Compare the stats of multiple players in Hypixel Bedwars. See how you stack up against your friends and rivals. Chart any combination of statistic (FKDR, wins, final kills, ...), players, gamemodes, and session/overall stats."
            />
            <UserMultiSelect
                uuids={uuids}
                onSubmit={(uuids) => {
                    navigate({
                        search: (oldSearch) => {
                            return {
                                ...oldSearch,
                                uuids,
                            };
                        },
                    }).catch((error: unknown) => {
                        // TODO: Handle error
                        console.error(
                            "Failed to update search params: uuids",
                            error,
                        );
                    });
                }}
            />
            <Stack direction="row" gap={1}>
                <Select
                    value={gamemodes}
                    label="Gamemodes"
                    aria-label="Gamemodes"
                    multiple
                    fullWidth
                    onChange={(event) => {
                        const newGamemodes = event.target
                            .value as GamemodeKey[];
                        navigate({
                            search: (oldSearch) => ({
                                ...oldSearch,
                                gamemodes: newGamemodes,
                            }),
                        }).catch((error: unknown) => {
                            // TODO: Handle error
                            console.error(
                                "Failed to update search params: gamemodes",
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
                    value={stats}
                    multiple
                    label="Stat"
                    aria-label="Stat"
                    fullWidth
                    onChange={(event) => {
                        const newStats = event.target.value as StatKey[];
                        navigate({
                            search: (oldSearch) => ({
                                ...oldSearch,
                                stats: newStats,
                            }),
                        }).catch((error: unknown) => {
                            // TODO: Handle error
                            console.error(
                                "Failed to update search params: stats",
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

            <Stack
                direction="row"
                gap={1}
                alignItems="center"
                justifyContent="space-between"
            >
                <Stack direction="row" gap={1} flexWrap="wrap">
                    {timeFilterOptions.map((option) => {
                        const selected =
                            option.start.toISOString() ===
                                start.toISOString() &&
                            option.end.toISOString() === end.toISOString();
                        return (
                            <RouterLinkChip
                                {
                                    /* This seems to work, but TS won't let me. Guessing it is the chip + link props colliding a bit */
                                    ...{ component: "a" }
                                }
                                key={option.label}
                                label={option.label}
                                variant="outlined"
                                color={selected ? "primary" : "default"}
                                from="/history/explore"
                                to="/history/explore"
                                search={(oldSearch) => ({
                                    ...oldSearch,
                                    start: option.start,
                                    end: option.end,
                                })}
                            />
                        );
                    })}
                </Stack>
                <Stack direction="row" gap={1}>
                    <DateTimePicker
                        label="Start"
                        value={dayjs(start)}
                        onChange={(newDate) => {
                            if (newDate === null) {
                                return;
                            }
                            navigate({
                                search: (oldSearch) => ({
                                    ...oldSearch,
                                    start: newDate.toDate(),
                                }),
                            }).catch((error: unknown) => {
                                // TODO: Handle error
                                console.error(
                                    "Failed to update search params: start",
                                    error,
                                );
                            });
                        }}
                    />
                    <DateTimePicker
                        label="End"
                        value={dayjs(end)}
                        onChange={(newDate) => {
                            if (newDate === null) {
                                return;
                            }
                            navigate({
                                search: (oldSearch) => ({
                                    ...oldSearch,
                                    end: newDate.toDate(),
                                }),
                            }).catch((error: unknown) => {
                                // TODO: Handle error
                                console.error(
                                    "Failed to update search params: end",
                                    error,
                                );
                            });
                        }}
                    />
                </Stack>
            </Stack>

            <Stack
                direction="row"
                gap={1}
                alignItems="center"
                justifyContent="space-between"
            >
                <Stack direction="row" gap={1} alignItems="center">
                    <HistoryChartTitle
                        uuids={uuids}
                        gamemodes={gamemodes}
                        stats={stats}
                        variants={variants}
                    />
                    <Tooltip
                        id="go-to-session-page-tooltip"
                        title={goToSessionPageTooltip}
                    >
                        {/* Make the span tabbable when the button is disabled so you can get to it and see the tooltip */}
                        <span tabIndex={canGoToSessionPage ? undefined : 0}>
                            <RouterLinkIconButton
                                aria-labelledby="go-to-session-page-tooltip"
                                disabled={!canGoToSessionPage}
                                size="small"
                                color="primary"
                                to="/session"
                                search={{
                                    uuid: uuids[0],
                                    gamemode: gamemodes[0],
                                    stat: stats[0],
                                    variantSelection,
                                    timeIntervalDefinition: {
                                        type: "until",
                                        date: sessionPageEndDate,
                                    },
                                    sessionTableMode: "total",
                                }}
                            >
                                <QueryStats />
                            </RouterLinkIconButton>
                        </span>
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
                        from="/history/explore"
                        to="/history/explore"
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
                        from="/history/explore"
                        to="/history/explore"
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
                        from="/history/explore"
                        to="/history/explore"
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
            <Stack flexGrow={1} paddingBottom={3}>
                <HistoryChart
                    start={start}
                    end={end}
                    uuids={uuids}
                    gamemodes={gamemodes}
                    stats={stats}
                    variants={variants}
                    limit={limit}
                />
            </Stack>
        </Stack>
    );
}
