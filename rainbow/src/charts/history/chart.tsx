import {
    CartesianGrid,
    Line,
    LineChart,
    type LineProps,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from "recharts";
import { GamemodeKey, StatKey, VariantKey } from "./types";
import React from "react";
import { ChartData, generateChartData } from "./data";
import { History } from "@/queries/history";
import { makeDataKey } from "./dataKeys";
import { useUUIDToUsername } from "@/queries/username";

interface HistoryChartProps {
    start: Date;
    end: Date;
    histories: History[];
    gamemodes: GamemodeKey[];
    stats: StatKey[];
    variant: VariantKey;
}

type TimeDenomination = "year" | "month" | "day" | "hour";

const getSmallestTimeDenomination = (
    chartData: ChartData,
): TimeDenomination => {
    if (chartData.length < 2) {
        return "hour";
    }
    const startDate = new Date(chartData[0].queriedAt);
    const endDate = new Date(chartData[chartData.length - 1].queriedAt);

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

const getStatDisplayName = (stat: StatKey): string => {
    switch (stat) {
        case "experience":
            return "Experience";
        case "stars":
            return "Stars";
        case "kills":
            return "Kills";
        case "deaths":
            return "Deaths";
        case "finalKills":
            return "Final Kills";
        case "finalDeaths":
            return "Final Deaths";
        case "bedsBroken":
            return "Beds Broken";
        case "bedsLost":
            return "Beds Lost";
        case "winstreak":
            return "Winstreak";
        case "wins":
            return "Wins";
        case "losses":
            return "Losses";
        case "gamesPlayed":
            return "Games Played";
        case "kdr":
            return "Kill/Death Ratio";
        case "fkdr":
            return "Final Kill/Death Ratio";
        case "index":
            return "Index (FKDR^2 * Stars)";
    }
};

const getGamemodeDisplayName = (gamemode: GamemodeKey): string => {
    switch (gamemode) {
        case "overall":
            return "Overall";
        case "solo":
            return "Solo";
        case "doubles":
            return "Doubles";
        case "threes":
            return "Threes";
        case "fours":
            return "Fours";
    }
};

const getVariantDisplayName = (variant: VariantKey): string => {
    switch (variant) {
        case "session":
            // TODO: Show daily/weekly/etc?
            return "Session";
        case "overall":
            return "Overall";
    }
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
): string => {
    if (!uuid.shown && !stat.shown && !gamemode.shown && !variant.shown) {
        return getStatDisplayName(stat.value);
    }

    let displayName = "";
    if (uuid.shown) {
        displayName += `${uuid.value}'s `;
    }

    if (
        gamemode.shown &&
        gamemode.value !== "overall" &&
        (!stat.shown || (stat.value !== "stars" && stat.value !== "experience"))
    ) {
        displayName += `${getGamemodeDisplayName(gamemode.value)} `;
    }

    if (variant.shown && variant.value !== "overall") {
        displayName += `${getVariantDisplayName(variant.value)} `;
    }

    if (stat.shown) {
        displayName += `${getStatDisplayName(stat.value)} `;
    }

    return displayName.slice(0, -1);
};

const renderTime = (
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
                hour: "numeric",
                minute: "numeric",
            });
        case "hour":
            return date.toLocaleString(undefined, {
                hour: "numeric",
                minute: "numeric",
                second: "numeric",
            });
    }
};

export const HistoryChart: React.FC<HistoryChartProps> = ({
    start,
    end,
    histories,
    gamemodes,
    stats,
    variant,
}) => {
    const uuids = React.useMemo(() => {
        return histories
            .map((history) => {
                if (history.length === 0) {
                    return undefined;
                }
                return history[0].uuid;
            })
            .filter((uuid) => uuid !== undefined);
    }, [histories]);

    const chartData = React.useMemo(() => {
        return generateChartData(histories);
    }, [histories]);

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

    if (chartData.length === 0) {
        return <div>No data</div>;
    }

    const smallestTimeDenomination = getSmallestTimeDenomination(chartData);

    return (
        <>
            <h3>
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
                        value: variant,
                        shown: true,
                    },
                )}
                {stats.length > 1 ? " Stats" : ""}
            </h3>
            <ResponsiveContainer
                minHeight={300}
                maxHeight={1000}
                minWidth={100}
            >
                <LineChart width={500} height={300} data={chartData}>
                    <XAxis
                        type="number"
                        domain={[start.getTime(), end.getTime()]}
                        scale="linear"
                        dataKey="queriedAt"
                        tickFormatter={(time: number) => {
                            return renderTime(time, smallestTimeDenomination);
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
                        variant,
                        uuidToUsername,
                    })}
                    <Tooltip
                        labelFormatter={(time: number) => {
                            return renderTime(time, smallestTimeDenomination);
                        }}
                    />
                </LineChart>
            </ResponsiveContainer>
        </>
    );
};

interface LinesProps {
    uuids: string[];
    gamemodes: GamemodeKey[];
    stats: StatKey[];
    variant: VariantKey;
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
    variant,
    uuidToUsername,
}: LinesProps): React.ReactNode[] => {
    let index = 0;
    return uuids.flatMap((uuid) => {
        return stats.flatMap((stat) => {
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
                                shown: false,
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
                const dataKey = makeDataKey({ uuid, gamemode, stat, variant });
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
                                shown: false,
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
};
