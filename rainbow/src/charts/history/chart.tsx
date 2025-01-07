import {
    CartesianGrid,
    Line,
    LineChart,
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

interface HistoryChartProps {
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
            return "Daily";
    }
};

const contextAwareStatDisplayName = (
    uuid: string,
    stat: StatKey,
    gamemode: GamemodeKey,
    variant: VariantKey,
    showStat: boolean,
    showUUID: boolean,
    showGamemodes: boolean,
    showVariant: boolean,
): string => {
    if (!showStat && !showUUID && !showGamemodes && !showVariant) {
        return getStatDisplayName(stat);
    }

    let displayName = "";
    if (showUUID) {
        // TODO: Get player name
        if (!showStat && !showGamemodes && !showVariant) {
            return uuid;
        }
        displayName += `${uuid}'s `;
    }

    if (
        showGamemodes &&
        gamemode !== "overall" &&
        stat !== "stars" &&
        stat !== "experience"
    ) {
        displayName += `${getGamemodeDisplayName(gamemode)} `;
    }

    if (showVariant) {
        displayName += `${getVariantDisplayName(variant)} `;
    }

    if (showStat) {
        displayName += `${getStatDisplayName(stat)} `;
    }

    return displayName.slice(0, -1);
};

export const HistoryChart: React.FC<HistoryChartProps> = ({
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

    if (uuids.length === 0 || stats.length === 0 || gamemodes.length === 0) {
        return <div>No data</div>;
    }

    if (chartData.length === 0) {
        return <div>No data</div>;
    }

    const smallestTimeDenomination = getSmallestTimeDenomination(chartData);

    return (
        <>
            <h3>
                {contextAwareStatDisplayName(
                    uuids[0],
                    stats[0],
                    gamemodes[0],
                    variant,
                    uuids.length === 1,
                    stats.length === 1,
                    gamemodes.length === 1,
                    true,
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
                        scale="linear"
                        dataKey="queriedAt"
                        tickFormatter={(time: number) => {
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
                        }}
                    />
                    <YAxis />
                    <CartesianGrid stroke="#eee" strokeDasharray="5 5" />
                    {renderLines({
                        uuids,
                        gamemodes,
                        stats,
                        variant,
                    })}
                    <Tooltip /*content={() => "Label"}*/ />
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
}

const renderLines = ({
    uuids,
    gamemodes,
    stats,
    variant,
}: LinesProps): React.ReactNode[] => {
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
                // TODO: Pass data directly to line instead of merging it and passing it to the chart
                return (
                    <Line
                        key={dataKey}
                        name={contextAwareStatDisplayName(
                            uuid,
                            stat,
                            "overall",
                            variant,
                            stats.length > 1,
                            uuids.length > 1,
                            gamemodes.length > 1,
                            false,
                        )}
                        type="monotone"
                        dataKey={dataKey}
                        stroke="#82ca9d"
                    />
                );
            }

            return gamemodes.map((gamemode) => {
                const dataKey = makeDataKey({ uuid, gamemode, stat, variant });
                return (
                    <Line
                        key={dataKey}
                        name={contextAwareStatDisplayName(
                            uuid,
                            stat,
                            gamemode,
                            variant,
                            stats.length > 1,
                            uuids.length > 1,
                            gamemodes.length > 1,
                            false,
                        )}
                        type="monotone"
                        dataKey={dataKey}
                        stroke="#82ca9d"
                    />
                );
            });
        });
    });
};
