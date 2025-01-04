import { historyQueryOptions } from "@/queries/history";
import { useQuery } from "@tanstack/react-query";
import { createLazyFileRoute } from "@tanstack/react-router";
import React from "react";
import {
    CartesianGrid,
    Line,
    LineChart,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from "recharts";

export const Route = createLazyFileRoute("/")({
    component: Index,
});

function Index() {
    const { data, status, error } = useQuery(historyQueryOptions);
    const chartData = React.useMemo(() => {
        if (!data) {
            return [];
        }
        const filteredData = data.filter(
            (item) => item.dataFormatVersion === 1,
        );
        if (filteredData.length === 0) {
            return [];
        }

        const firstEntry = filteredData[0];

        return filteredData.map((item) => {
            let sessionKills = 0;
            if (
                item.overall.kills !== null &&
                firstEntry.overall.kills !== null
            ) {
                sessionKills = item.overall.kills - firstEntry.overall.kills;
            }

            let sessionFinals = 0;
            if (
                item.overall.finalKills !== null &&
                firstEntry.overall.finalKills !== null
            ) {
                sessionFinals =
                    item.overall.finalKills - firstEntry.overall.finalKills;
            }

            let sessionFinalDeaths = 0;
            if (
                item.overall.finalDeaths !== null &&
                firstEntry.overall.finalDeaths !== null
            ) {
                sessionFinalDeaths =
                    item.overall.finalDeaths - firstEntry.overall.finalDeaths;
            }

            const sessionFinalKDR =
                sessionFinalDeaths === 0
                    ? sessionFinals
                    : sessionFinals / sessionFinalDeaths;

            return {
                queriedAt: item.queriedAt.getTime(),
                finals: sessionFinals,
                kills: sessionKills,
                finalKDR: sessionFinalKDR,
            };
        });
    }, [data]);
    return (
        <div>
            <h3>Welcome Home!</h3>
            {status} {error?.name} {error?.message}
            <br />
            {data?.map((item) => (
                <>
                    {item.id}: {item.overall.finalKills}
                    <br />
                </>
            ))}
            <ResponsiveContainer
                minHeight={300}
                maxHeight={1000}
                minWidth={100}
            >
                <LineChart width={500} height={300} data={chartData}>
                    <XAxis
                        scale="linear"
                        dataKey="queriedAt"
                        tickFormatter={(time: number) =>
                            // TODO: Do formatting based on the range of the data (time only when within a day)
                            new Date(time).toLocaleString(undefined, {
                                dateStyle: "medium",
                            })
                        }
                    />
                    <YAxis />
                    <CartesianGrid stroke="#eee" strokeDasharray="5 5" />
                    {/*
                    <Line name="finals" type="monotone" dataKey="finals" stroke="#8884d8" />
                    <Line name="kills" type="monotone" dataKey="kills" stroke="#82ca9d" />
                        */}
                    <Line
                        name="FKDR"
                        type="monotone"
                        dataKey="finalKDR"
                        stroke="#82ca9d"
                    />
                    <Tooltip /*content={() => "Label"}*/ />
                </LineChart>
            </ResponsiveContainer>
        </div>
    );
}
