import {
    Area,
    AreaChart,
    CartesianGrid,
    Legend,
    Line,
    LineChart,
    ReferenceArea,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from "recharts";
import {
    type GamemodeKey,
    type StatKey,
    type VariantKey,
} from "#stats/keys.ts";
import React from "react";
import { generateChartData } from "./data.ts";
import { makeDataKey } from "./dataKeys.ts";
import { useUUIDToUsername } from "#queries/username.ts";
import { useQueries, useQuery } from "@tanstack/react-query";
import { getHistoryQueryOptions } from "#queries/history.ts";
import {
    getFullStatLabel,
    getGamemodeLabel,
    getVariantLabel,
} from "#stats/labels.ts";
import { Typography, useTheme } from "@mui/material";
import { useSynchronizeCharts } from "#contexts/ChartSynchronizer/hooks.ts";

interface HistoryChartProps {
    start: Date;
    end: Date;
    uuids: readonly string[];
    gamemodes: readonly GamemodeKey[];
    stats: readonly StatKey[];
    variants: readonly VariantKey[];
    limit: number;
}

type TimeDenomination = "year" | "month" | "day" | "hour";

const getSmallestTimeDenomination = (
    startDate: Date,
    endDate: Date,
): TimeDenomination => {
    const differentYear = startDate.getFullYear() !== endDate.getFullYear();
    const differentMonth =
        startDate.getMonth() !== endDate.getMonth() || differentYear;
    const differentDay =
        startDate.getDate() !== endDate.getDate() || differentMonth;

    if (differentYear) {
        return "year";
    }
    if (differentMonth) {
        return "month";
    }
    if (differentDay) {
        return "day";
    }
    return "hour";
};

// string overrides all of these string unions, but we keep them here to be explicit about our intentions
// eslint-disable-next-line @typescript-eslint/no-redundant-type-constituents
interface KeyConfig<T extends StatKey | GamemodeKey | VariantKey | string> {
    value: T;
    shown: boolean;
}

const contextAwareStatDisplayName = (
    uuid: KeyConfig<string>,
    stat: KeyConfig<StatKey>,
    gamemode: KeyConfig<GamemodeKey>,
    variant: KeyConfig<VariantKey>,
    alwaysIncludePossessive = false,
): string => {
    if (!uuid.shown && !stat.shown && !gamemode.shown && !variant.shown) {
        return getFullStatLabel(stat.value, true);
    }

    const gamemodeShown =
        gamemode.shown &&
        gamemode.value !== "overall" &&
        (!stat.shown ||
            (stat.value !== "stars" && stat.value !== "experience"));

    let displayName = "";
    if (uuid.shown) {
        if (
            !stat.shown &&
            !gamemodeShown &&
            !variant.shown &&
            !alwaysIncludePossessive
        ) {
            return uuid.value;
        }
        displayName += `${uuid.value}'s `;
    }

    if (variant.shown) {
        displayName += `${getVariantLabel(variant.value, displayName === "")} `;
    }

    if (gamemodeShown) {
        displayName += `${getGamemodeLabel(gamemode.value, displayName === "")} `;
    }

    if (stat.shown) {
        displayName += `${getFullStatLabel(stat.value, displayName === "")} `;
    }

    return displayName.slice(0, -1);
};

const renderTimeShort = (
    time: number,
    smallestTimeDenomination: TimeDenomination,
): string => {
    const date = new Date(time);
    switch (smallestTimeDenomination) {
        case "year":
            return date.toLocaleString(undefined, {
                dateStyle: "medium",
            });
        case "month":
            return date.toLocaleString(undefined, {
                month: "short",
                day: "numeric",
            });
        case "day":
            return date.toLocaleString(undefined, {
                month: "short",
                day: "numeric",
            });
        case "hour":
            return date.toLocaleString(undefined, {
                hour: "numeric",
                minute: "numeric",
                second: "numeric",
            });
    }
};

const renderTimeFull = (time: number): string => {
    const date = new Date(time);
    return date.toLocaleString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "numeric",
        second: "numeric",
    });
};

interface HistoryChartTitleProps {
    uuids: readonly string[];
    gamemodes: readonly GamemodeKey[];
    stats: readonly StatKey[];
    variants: readonly VariantKey[];
}

export const HistoryChartTitle: React.FC<HistoryChartTitleProps> = ({
    uuids,
    gamemodes,
    stats,
    variants,
}) => {
    const uuidToUsername = useUUIDToUsername(uuids);
    return (
        <Typography variant="h6">
            {contextAwareStatDisplayName(
                {
                    // TODO: Display error state if missing uuid
                    value: uuidToUsername[uuids[0]] ?? "",
                    shown: uuids.length === 1,
                },
                {
                    value: stats[0],
                    shown: stats.length === 1,
                },
                {
                    value: gamemodes[0],
                    shown: gamemodes.length === 1,
                },
                {
                    value: variants[0],
                    shown: variants.length === 1,
                },
                true,
            )}
            {stats.length > 1 ? " Stats" : ""}
        </Typography>
    );
};
export const HistoryChart: React.FC<HistoryChartProps> = ({
    start,
    end,
    uuids,
    gamemodes,
    stats,
    variants,
    limit,
}) => {
    const theme = useTheme();
    const historyQueries = useQueries({
        queries: uuids.map((uuid) =>
            getHistoryQueryOptions({ uuid, start, end, limit }),
        ),
    });

    const histories = historyQueries
        .filter((query) => query.status === "success")
        .map((query) => query.data);

    const chartData = generateChartData(histories);

    const uuidToUsername = useUUIDToUsername(uuids);

    if (uuids.length === 0) {
        return <div>Select at least one user</div>;
    }

    if (stats.length === 0) {
        return <div>Select at least one statistic</div>;
    }

    if (gamemodes.length === 0) {
        return <div>Select at least one gamemode or overall</div>;
    }

    if (variants.length === 0) {
        return <div>Select at least one session or overall</div>;
    }

    if (chartData.length === 0) {
        return <div>No data</div>;
    }

    const currentDate = new Date();

    const smallestTimeDenomination = getSmallestTimeDenomination(start, end);

    // Linechart requires a mutable array for some reason. Make a copy here so we can mutate it.
    const mutableChartData = [...chartData];

    return (
        <ResponsiveContainer minHeight={300} minWidth={100}>
            <LineChart
                data={mutableChartData}
                syncId="history-chart"
                syncMethod="value"
            >
                <XAxis
                    type="number"
                    domain={[start.getTime(), end.getTime()]}
                    scale="linear"
                    dataKey="queriedAt"
                    tickFormatter={(time: number) => {
                        return renderTimeShort(time, smallestTimeDenomination);
                    }}
                    ticks={new Array(10).fill(0).map((_, i) => {
                        const startTime = start.getTime();
                        const endTime = end.getTime();
                        return startTime + ((endTime - startTime) / 9) * i;
                    })}
                />
                <YAxis />
                <CartesianGrid stroke="#eee" strokeDasharray="5 5" />
                {renderLines({
                    uuids,
                    gamemodes,
                    stats,
                    variants,
                    uuidToUsername,
                })}
                {/* Future marker */}
                <ReferenceArea
                    x1={currentDate.getTime()}
                    x2={end.getTime()}
                    stroke="#efefef"
                    fill="#e0e0e0"
                />
                <Legend />
                <Tooltip
                    labelFormatter={(time: number) => {
                        return renderTimeFull(time);
                    }}
                    contentStyle={{
                        backgroundColor: theme.palette.background.paper,
                    }}
                    itemStyle={{ color: theme.palette.text.primary }}
                />
            </LineChart>
        </ResponsiveContainer>
    );
};

interface SimpleHistoryChartProps {
    start: Date;
    end: Date;
    uuid: string;
    gamemode: GamemodeKey;
    stat: StatKey;
    variant: VariantKey;
    limit: number;
}

export const SimpleHistoryChart: React.FC<SimpleHistoryChartProps> = ({
    start,
    end,
    uuid,
    gamemode,
    stat,
    variant,
    limit,
}) => {
    const { data: history } = useQuery(
        getHistoryQueryOptions({ uuid, start, end, limit }),
    );

    const theme = useTheme();

    const chartData = React.useMemo(() => {
        if (!history) {
            return [];
        }
        return generateChartData([history]);
    }, [history]);

    const uuidToUsername = useUUIDToUsername([uuid]);

    const currentDate = new Date();

    // Linechart requires a mutable array for some reason. Make a copy here so we can mutate it.
    const mutableChartData = [...chartData];

    const dataKey = makeDataKey({
        uuid,
        gamemode,
        stat,
        variant,
    });

    const { yMax } = useSynchronizeCharts(chartData, dataKey);

    return (
        <ResponsiveContainer minHeight={50} maxHeight={50} minWidth={100}>
            <AreaChart
                data={mutableChartData}
                syncId="history-chart"
                syncMethod="value"
            >
                <XAxis
                    type="number"
                    domain={[start.getTime(), end.getTime()]}
                    hide
                    scale="linear"
                    dataKey="queriedAt"
                />
                <YAxis
                    type="number"
                    domain={[0, yMax ?? "auto"]}
                    hide
                    scale="linear"
                />

                {/* Chart outline */}
                <ReferenceArea
                    x1={start.getTime()}
                    x2={end.getTime()}
                    stroke="#efefef"
                    fillOpacity={0}
                />
                {/* Chart data */}
                <Area
                    key={dataKey}
                    name={contextAwareStatDisplayName(
                        {
                            // TODO: Display error state if missing uuid
                            value: uuidToUsername[uuid] ?? "",
                            shown: false,
                        },
                        {
                            value: stat,
                            shown: true,
                        },
                        {
                            value: gamemode,
                            shown: true,
                        },
                        {
                            value: variant,
                            shown: true,
                        },
                    )}
                    type="monotone"
                    dataKey={dataKey}
                    stroke={theme.palette.primary.main}
                    fill={theme.palette.primary.main}
                    dot={false}
                    connectNulls
                />
                {/* Future marker */}
                <ReferenceArea
                    x1={currentDate.getTime()}
                    x2={end.getTime()}
                    stroke="#efefef"
                    fill="#e0e0e0"
                />

                <Tooltip
                    // TODO: Nicer tooltip
                    content={({ active, payload }) => {
                        if (!active || !payload.length) {
                            return null;
                        }

                        const item: unknown = payload[0];
                        if (typeof item !== "object" || item === null) {
                            return null;
                        }

                        if (!("value" in item)) {
                            return null;
                        }

                        const value = item.value;
                        if (typeof value !== "number") {
                            return null;
                        }

                        // TODO: Better number formatting
                        return value.toLocaleString();
                    }}
                    contentStyle={{
                        backgroundColor: theme.palette.background.paper,
                    }}
                    itemStyle={{ color: theme.palette.text.primary }}
                />
            </AreaChart>
        </ResponsiveContainer>
    );
};

interface LinesProps {
    uuids: readonly string[];
    gamemodes: readonly GamemodeKey[];
    stats: readonly StatKey[];
    variants: readonly VariantKey[];
    uuidToUsername: Record<string, string | undefined>;
}

const STROKES = [
    "#82ca9d",
    "#8884d8",
    "#ff7300",
    "#413ea0",
    "#ff0000",
    "#00ff00",
    "#0000ff",
    "#ff00ff",
    "#00ffff",
];

const DASHES = ["0", "5 5", "10 5", "5 10", "5 2", "10 10"];

const getLineStyle = (index: number) => {
    // TODO: Get line style based on hash of dataKey
    // TODO: Make linestyles more deterministic (hash of datakey/one color per player/...)
    return {
        stroke: STROKES[index % STROKES.length],
        strokeDasharray:
            DASHES[Math.floor(index / STROKES.length) % DASHES.length],
    } as const;
};

const renderLines = ({
    uuids,
    gamemodes,
    stats,
    variants,
    uuidToUsername,
}: LinesProps): React.ReactNode[] => {
    let index = 0;
    return uuids.flatMap((uuid) => {
        return stats.flatMap((stat) => {
            return variants.flatMap((variant) => {
                if (stat === "stars" || stat === "experience") {
                    // Only create one line for stars, not one for each gamemode
                    const dataKey = makeDataKey({
                        uuid,
                        gamemode: "overall",
                        stat,
                        variant,
                    });
                    return (
                        <Line
                            key={dataKey}
                            name={contextAwareStatDisplayName(
                                {
                                    // TODO: Display error state if missing uuid
                                    value: uuidToUsername[uuid] ?? "",
                                    shown: uuids.length > 1,
                                },
                                {
                                    value: stat,
                                    shown: stats.length > 1,
                                },
                                {
                                    value: "overall",
                                    shown: gamemodes.length > 1,
                                },
                                {
                                    value: variant,
                                    shown: variants.length > 1,
                                },
                            )}
                            type="monotone"
                            dataKey={dataKey}
                            connectNulls
                            {...getLineStyle(index++)}
                        />
                    );
                }

                return gamemodes.map((gamemode) => {
                    const dataKey = makeDataKey({
                        uuid,
                        gamemode,
                        stat,
                        variant,
                    });
                    return (
                        <Line
                            key={dataKey}
                            name={contextAwareStatDisplayName(
                                {
                                    // TODO: Display error state if missing uuid
                                    value: uuidToUsername[uuid] ?? "",
                                    shown: uuids.length > 1,
                                },
                                {
                                    value: stat,
                                    shown: stats.length > 1,
                                },
                                {
                                    value: gamemode,
                                    shown: gamemodes.length > 1,
                                },
                                {
                                    value: variant,
                                    shown: variants.length > 1,
                                },
                            )}
                            type="monotone"
                            dataKey={dataKey}
                            {...getLineStyle(index++)}
                            connectNulls
                        />
                    );
                });
            });
        });
    });
};
