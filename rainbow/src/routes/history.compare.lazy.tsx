import { HistoryChart } from "@/charts/history/chart";
import { getHistoryQueryOptions } from "@/queries/history";
import { useQueries } from "@tanstack/react-query";
import { createLazyFileRoute, getRouteApi } from "@tanstack/react-router";
import { useMemo } from "react";

export const Route = createLazyFileRoute("/history/compare")({
    component: Index,
});

const route = getRouteApi("/history/compare");

function Index() {
    const { uuids, stats, gamemodes, variant, start, end, limit } =
        route.useSearch();
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
                gamemodes={gamemodes}
                stats={stats}
                variant={variant}
            />
        </div>
    );
}
