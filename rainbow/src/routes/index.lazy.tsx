import { HistoryChart } from "@/charts/history/chart";
import { getHistoryQueryOptions } from "@/queries/history";
import { useQueries } from "@tanstack/react-query";
import { createLazyFileRoute } from "@tanstack/react-router";
import { useMemo } from "react";

export const Route = createLazyFileRoute("/")({
    component: Index,
});

function Index() {
    const start = new Date("2024-11-01T00:00:00Z");
    const end = new Date("2025-06-01T00:00:00Z");
    const limit = 100;
    const uuids = [
        "a937646b-f115-44c3-8dbf-9ae4a65669a0",
        "ac04f297-f74c-44de-a24e-0083936ac59a",
    ];
    const historyQueries = useQueries({
        queries: uuids.map((uuid) =>
            getHistoryQueryOptions({ uuid, start, end, limit }),
        ),
    });

    /*
    const { data, status, error } = useQueries({
    if (status === "pending") {
        return <div>Loading...</div>;
    }

    if (status === "error") {
        return <div>Error: {error.message}</div>;
    }
    */

    const finishedHistories = useMemo(() => {
        return historyQueries
            .filter((query) => query.status === "success")
            .map((query) => query.data);
    }, [historyQueries]);

    return (
        <div>
            <h3>Welcome Home!</h3>
            <HistoryChart
                histories={finishedHistories}
                gamemodes={["overall"]}
                stats={["stars", "finalKills"]}
                variant="session"
            />
        </div>
    );
}
