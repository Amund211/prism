import { HistoryChart, HistoryChartTitle } from "#charts/history/chart.tsx";
import { UserSearch } from "#components/UserSearch.tsx";
import { useUUIDToUsername } from "#queries/username.ts";
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
    Skeleton,
    Stack,
    ToggleButton,
    ToggleButtonGroup,
    Tooltip,
} from "@mui/material";
import {
    createLazyFileRoute,
    createLink,
    getRouteApi,
} from "@tanstack/react-router";
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

export const Route = createLazyFileRoute("/history/compare")({
    component: Index,
});

const route = getRouteApi("/history/compare");

const RouterLinkChip = createLink(Chip);
const RouterLinkIconButton = createLink(IconButton);

function Index() {
    const { uuids, stats, gamemodes, variantSelection, start, end, limit } =
        route.useSearch();
    const navigate = route.useNavigate();

    const variants =
        variantSelection === "both"
            ? (["session", "overall"] as const)
            : ([variantSelection] as const);

    const uuidToUsername = useUUIDToUsername(uuids);

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
            <UserSearch
                placeholder="Add user..."
                onSubmit={(uuid) => {
                    navigate({
                        search: (oldSearch) => {
                            if (oldSearch.uuids.includes(uuid)) {
                                return oldSearch;
                            }
                            return {
                                ...oldSearch,
                                uuids: [...oldSearch.uuids, uuid],
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
            <Stack direction="row" gap={1} flexWrap="wrap">
                {uuids.length === 0 && (
                    <Tooltip title="Use the search bar to add users.">
                        <span tabIndex={0}>
                            <Chip
                                disabled
                                variant="outlined"
                                label="No users added"
                            />
                        </span>
                    </Tooltip>
                )}
                {uuids.map((uuid) => (
                    <Chip
                        key={uuid}
                        label={
                            uuidToUsername[uuid] ?? (
                                <Skeleton variant="text" width={60} />
                            )
                        }
                        variant="outlined"
                        color="primary"
                        avatar={
                            <img
                                style={{ backgroundColor: "rgba(0, 0, 0, 0)" }}
                                // TODO: Attribution - https://crafatar.com/#meta-attribution
                                src={`https://crafatar.com/renders/head/${uuid}?overlay`}
                            />
                        }
                        onDelete={() => {
                            navigate({
                                search: (oldSearch) => ({
                                    ...oldSearch,
                                    uuids: oldSearch.uuids.filter(
                                        (u) => u !== uuid,
                                    ),
                                }),
                            }).catch((error: unknown) => {
                                // TODO: Handle error
                                console.error(
                                    "Failed to update search params: variantSelection",
                                    error,
                                );
                            });
                        }}
                    />
                ))}
            </Stack>
            <Stack direction="row" gap={1}>
                <Select
                    value={gamemodes}
                    label="Gamemodes"
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
                                from="/history/compare"
                                to="/history/compare"
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
                    <Tooltip title={goToSessionPageTooltip}>
                        {/* Make the span tabbable when the button is disabled so you can get to it and see the tooltip */}
                        <span tabIndex={canGoToSessionPage ? undefined : 0}>
                            <RouterLinkIconButton
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
                    onChange={(
                        _,
                        newSelection: "overall" | "session" | "both" | null,
                    ) => {
                        if (newSelection === null) {
                            return;
                        }
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
                    <ToggleButton value="overall">
                        {getVariantLabel("overall", true)}
                    </ToggleButton>
                    <ToggleButton value="session">
                        {getVariantLabel("session", true)}
                    </ToggleButton>
                    <ToggleButton value="both">Both</ToggleButton>
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
