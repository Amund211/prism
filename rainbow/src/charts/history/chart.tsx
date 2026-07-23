import { Typography, useTheme } from "@mui/material";
import { useQueries, useQuery } from "@tanstack/react-query";
import React from "react";
import type { ReactNode } from "react";
import {
    Area,
    AreaChart,
    CartesianGrid,
    Legend,
    Line,
    LineChart,
    ReferenceArea,
    Tooltip,
    XAxis,
    YAxis,
} from "recharts";

import { useSynchronizeCharts } from "#contexts/ChartSynchronizer/hooks.ts";
import { useAssume } from "#hooks/useAssumption.ts";
import { getHistoryQueryOptions } from "#queries/history.ts";
import { useUUIDToUsername } from "#queries/username.ts";
import { formatStatValue } from "#stats/format.ts";
import type { GamemodeKey, StatKey, VariantKey } from "#stats/keys.ts";
import { getFullStatLabel, getGamemodeLabel, getVariantLabel } from "#stats/labels.ts";

import { generateChartData } from "./data.ts";
import { makeDataKey } from "./dataKeys.ts";

// Dash patterns cycled through once the colour palette wraps, so overlapping
// series stay distinguishable.
const DASHES = ["0", "5 5", "10 5", "5 10", "5 2", "10 10"];

interface LineStyle {
    readonly stroke: string;
    readonly strokeDasharray: string;
}

type LineStyleFn = (gamemode: GamemodeKey, index: number) => LineStyle;

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
    const differentMonth = startDate.getMonth() !== endDate.getMonth() || differentYear;
    const differentDay = startDate.getDate() !== endDate.getDate() || differentMonth;

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
// oxlint-disable-next-line @typescript-eslint/no-redundant-type-constituents
interface KeyConfig<T extends StatKey | GamemodeKey | VariantKey | string> {
    readonly value: T;
    readonly shown: boolean;
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
        (!stat.shown || (stat.value !== "stars" && stat.value !== "experience"));

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
        case "year": {
            return date.toLocaleString(undefined, {
                dateStyle: "medium",
            });
        }
        case "month": {
            return date.toLocaleString(undefined, {
                month: "short",
                day: "numeric",
            });
        }
        case "day": {
            return date.toLocaleString(undefined, {
                month: "short",
                day: "numeric",
            });
        }
        case "hour": {
            return date.toLocaleString(undefined, {
                hour: "numeric",
                minute: "numeric",
                second: "numeric",
            });
        }
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

    const assume = useAssume();

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

    // Comparing gamemodes (a single player/stat/variant) colours each line by
    // the gamemode's identity colour. Every other combination cycles the brand
    // rainbow, with dash patterns disambiguating once it wraps — this keeps
    // distinct lines distinct even when several share a hue.
    const colorByGamemode =
        uuids.length === 1 && stats.length === 1 && variants.length === 1;
    const { rainbow } = theme.palette;

    const lineStyle: LineStyleFn = (gamemode, index) => {
        if (colorByGamemode) {
            return { stroke: theme.palette.gamemode[gamemode], strokeDasharray: "0" };
        }
        return {
            stroke: rainbow[index % rainbow.length],
            strokeDasharray: DASHES[Math.floor(index / rainbow.length) % DASHES.length],
        };
    };

    // oxlint-disable-next-line eslint/no-use-before-define
    const { lines, statByDataKey } = renderLines({
        uuids,
        gamemodes,
        stats,
        variants,
        uuidToUsername,
        lineStyle,
    });

    return (
        <LineChart
            data={mutableChartData}
            responsive
            width="100%"
            height="100%"
            style={{ minHeight: 300, minWidth: 100 }}
            syncId="history-chart"
            syncMethod="value"
        >
            <XAxis
                type="number"
                domain={[start.getTime(), end.getTime()]}
                scale="linear"
                dataKey="queriedAt"
                stroke={theme.palette.divider}
                tick={{ fill: theme.palette.text.secondary, fontSize: 12 }}
                tickFormatter={(time: number) => {
                    return renderTimeShort(time, smallestTimeDenomination);
                }}
                ticks={Array.from({ length: 10 }).map((_, i) => {
                    const startTime = start.getTime();
                    const endTime = end.getTime();
                    return startTime + ((endTime - startTime) / 9) * i;
                })}
            />
            <YAxis
                stroke={theme.palette.divider}
                tick={{ fill: theme.palette.text.secondary, fontSize: 12 }}
            />
            <CartesianGrid stroke={theme.palette.divider} strokeDasharray="2 4" />
            {lines}
            {/* Future marker */}
            <ReferenceArea
                x1={currentDate.getTime()}
                x2={end.getTime()}
                stroke={theme.palette.divider}
                fill={theme.palette.textMuted}
                fillOpacity={0.12}
            />
            <Legend wrapperStyle={{ color: theme.palette.text.secondary }} />
            <Tooltip
                // oxlint-disable-next-line typescript/promise-function-async
                labelFormatter={(label: ReactNode) => {
                    if (typeof label === "number") {
                        return renderTimeFull(label);
                    }
                    assume(false, "Tooltip label is not a number", () => ({
                        time: label,
                        timeTypeof: typeof label,
                    }));
                    return label;
                }}
                formatter={(value, _name, item) => {
                    const stat = statByDataKey.get(String(item.dataKey));
                    return typeof value === "number" && stat !== undefined
                        ? formatStatValue(stat, value, { precision: "detailed" })
                        : value;
                }}
                contentStyle={{
                    backgroundColor: theme.palette.background.paper,
                    border: `1px solid ${theme.palette.divider}`,
                    borderRadius: 8,
                }}
                itemStyle={{ color: theme.palette.text.primary }}
                labelStyle={{ color: theme.palette.text.secondary }}
            />
        </LineChart>
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

    // Tint the sparkline with the gamemode's identity colour. "overall" resolves
    // to the brand primary via the theme, so the aggregate series matches the
    // explore chart and the rest of the UI — one source of truth.
    const seriesColor = theme.palette.gamemode[gamemode];
    // NOTE: Assume the id format is CSS-selector-safe
    const gradientId = `spark-${React.useId()}`;

    return (
        <AreaChart
            data={mutableChartData}
            responsive
            width="100%"
            height={50}
            style={{ minWidth: 100 }}
            syncId="history-chart"
            syncMethod="value"
        >
            <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={seriesColor} stopOpacity={0.32} />
                    <stop offset="100%" stopColor={seriesColor} stopOpacity={0} />
                </linearGradient>
            </defs>
            <XAxis
                type="number"
                domain={[start.getTime(), end.getTime()]}
                hide
                scale="linear"
                dataKey="queriedAt"
            />
            <YAxis type="number" domain={[0, yMax ?? "auto"]} hide scale="linear" />

            {/* Chart outline */}
            <ReferenceArea
                x1={start.getTime()}
                x2={end.getTime()}
                stroke={theme.palette.divider}
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
                stroke={seriesColor}
                fill={`url(#${gradientId})`}
                dot={false}
                connectNulls
            />
            {/* Future marker */}
            <ReferenceArea
                x1={currentDate.getTime()}
                x2={end.getTime()}
                stroke={theme.palette.divider}
                fill={theme.palette.textMuted}
                fillOpacity={0.12}
            />

            <Tooltip
                // TODO: Nicer tooltip
                content={({ active, payload }) => {
                    if (!active || payload.length === 0) {
                        return null;
                    }

                    const item: unknown = payload[0];
                    if (typeof item !== "object" || item === null) {
                        return null;
                    }

                    if (!("value" in item)) {
                        return null;
                    }

                    const { value } = item;
                    if (typeof value !== "number") {
                        return null;
                    }

                    return formatStatValue(stat, value, { precision: "detailed" });
                }}
                contentStyle={{
                    backgroundColor: theme.palette.background.paper,
                    border: `1px solid ${theme.palette.divider}`,
                    borderRadius: 8,
                }}
                itemStyle={{ color: theme.palette.text.primary }}
            />
        </AreaChart>
    );
};

interface LinesProps {
    readonly uuids: readonly string[];
    readonly gamemodes: readonly GamemodeKey[];
    readonly stats: readonly StatKey[];
    readonly variants: readonly VariantKey[];
    readonly uuidToUsername: Readonly<Record<string, string | undefined>>;
    readonly lineStyle: LineStyleFn;
}

const renderLines = ({
    uuids,
    gamemodes,
    stats,
    variants,
    uuidToUsername,
    lineStyle,
}: LinesProps): {
    lines: React.ReactNode[];
    statByDataKey: Map<string, StatKey>;
} => {
    let index = 0;
    // Authoritative dataKey → stat lookup, built where each line is created so
    // the tooltip formatter never has to reverse-parse the dataKey string
    // (uuids and the "4v4" gamemode make splitting fragile).
    const statByDataKey = new Map<string, StatKey>();
    const lines = uuids.flatMap((uuid) => {
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
                    statByDataKey.set(dataKey, stat);
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
                            // oxlint-disable-next-line react/jsx-props-no-spreading
                            {...lineStyle("overall", index++)}
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
                    statByDataKey.set(dataKey, stat);
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
                            // oxlint-disable-next-line react/jsx-props-no-spreading
                            {...lineStyle(gamemode, index++)}
                            connectNulls
                        />
                    );
                });
            });
        });
    });
    return { lines, statByDataKey };
};
