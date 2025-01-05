import { HistoryChart } from "@/charts/history/chart";
import { historyQueryOptions } from "@/queries/history";
import { useQuery } from "@tanstack/react-query";
import { createLazyFileRoute } from "@tanstack/react-router";

export const Route = createLazyFileRoute("/")({
    component: Index,
});

function Index() {
    const { data, status, error } = useQuery(historyQueryOptions);

    if (status === "pending") {
        return <div>Loading...</div>;
    }

    if (status === "error") {
        return <div>Error: {error.message}</div>;
    }

    return (
        <div>
            <h3>Welcome Home!</h3>
            <HistoryChart
                histories={[data]}
                gamemodes={["overall", "solo", "fours"]}
                stats={["stars", "finalKills", "finalDeaths", "kills"]}
                variant="session"
            />
        </div>
    );
}
