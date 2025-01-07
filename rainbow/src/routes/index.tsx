import { createFileRoute } from "@tanstack/react-router";
import { queryClient } from "@/queryClient";
import { getHistoryQueryOptions } from "@/queries/history";

export const Route = createFileRoute("/")({
    // loader: () => queryClient.ensureQueryData(getHistoryQueryOptions),
});
