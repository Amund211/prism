import { createFileRoute } from "@tanstack/react-router";
import { queryClient } from "@/queryClient";
import { historyQueryOptions } from "@/queries/history";

export const Route = createFileRoute("/")({
    loader: () => queryClient.ensureQueryData(historyQueryOptions),
});
