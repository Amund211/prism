import { createFileRoute } from "@tanstack/react-router";
import { queryClient } from "@/queryClient";
import { getHistoryQueryOptions } from "@/queries/history";
import { zodValidator } from "@tanstack/zod-adapter";
import { z } from "zod";
import {
    ALL_GAMEMODE_KEYS,
    ALL_STAT_KEYS,
    ALL_VARIANT_KEYS,
} from "@/charts/history/types";

const historyCompareSearchSchema = z.object({
    uuids: z.array(z.string()).min(1),
    start: z.coerce.date(),
    end: z.coerce.date(),
    limit: z.number().int().min(1).max(100),
    stats: z.enum(ALL_STAT_KEYS).array().min(1),
    gamemodes: z.enum(ALL_GAMEMODE_KEYS).array().min(1),
    variant: z.enum(ALL_VARIANT_KEYS),
});

export const Route = createFileRoute("/history/compare")({
    loaderDeps: ({ search: { uuids, start, end, limit } }) => ({
        uuids,
        start,
        end,
        limit,
    }),

    loader: ({ deps: { uuids, start, end, limit } }) => {
        Promise.all(
            uuids.map((uuid) =>
                queryClient.fetchQuery(
                    getHistoryQueryOptions({ uuid, start, end, limit }),
                ),
            ),
        ).catch((e: unknown) => {
            // TODO: Report error
            console.error(e);
        });
    },
    validateSearch: zodValidator(historyCompareSearchSchema),
});
