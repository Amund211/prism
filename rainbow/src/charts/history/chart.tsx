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
import { generateChartData } from "./data";
import { History } from "@/queries/history";
import { makeDataKey } from "./dataKeys";

interface HistoryChartProps {
    histories: History[];
    gamemodes: GamemodeKey[];
    stats: StatKey[];
    variant: VariantKey;
}

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

    if (chartData.length === 0) {
        return <div>No data</div>;
    }

    return (
        <ResponsiveContainer minHeight={300} maxHeight={1000} minWidth={100}>
            <LineChart width={500} height={300} data={chartData}>
                <XAxis
                    scale="linear"
                    dataKey="queriedAt"
                    tickFormatter={(time: number) => {
                        // TODO: Do formatting based on the range of the data (time only when within a day)
                        return new Date(time).toLocaleString(undefined, {
                            dateStyle: "medium",
                        });
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
                return (
                    <Line
                        key={dataKey}
                        name={stat}
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
                        name={stat}
                        type="monotone"
                        dataKey={dataKey}
                        stroke="#82ca9d"
                    />
                );
            });
        });
    });
};
