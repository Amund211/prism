import { createFileRoute } from "@tanstack/react-router";
import { queryClient } from "@/queryClient";
import { getHistoryQueryOptions } from "@/queries/history";
import { zodValidator } from "@tanstack/zod-adapter";
import { z } from "zod";
import {
    ALL_GAMEMODE_KEYS,
    ALL_STAT_KEYS,
    ALL_VARIANT_KEYS,
} from "@/stats/keys";
import { getUsernameQueryOptions } from "@/queries/username";

const defaultStart = new Date();
defaultStart.setHours(0, 0, 0, 0);
const defaultEnd = new Date();
defaultEnd.setHours(23, 59, 59, 999);

const historyCompareSearchSchema = z.object({
    // TODO: Read "preferred user" from local storage or similar
    uuids: z.array(z.string()).catch([]),
    start: z.coerce.date().catch(defaultStart),
    end: z.coerce.date().catch(defaultEnd),
    limit: z.number().int().min(1).max(50).catch(50),
    stats: z.enum(ALL_STAT_KEYS).array().catch(["fkdr"]),
    gamemodes: z.enum(ALL_GAMEMODE_KEYS).array().catch(["overall"]),
    variant: z.enum(ALL_VARIANT_KEYS).catch("session"),
});

export const Route = createFileRoute("/history/compare")({
    loaderDeps: ({ search: { uuids, start, end, limit } }) => ({
        uuids,
        start,
        end,
        limit,
    }),

    loader: ({ deps: { uuids, start, end, limit } }) => {
        // TODO: Rate limiting
        Promise.all([
            ...uuids.map((uuid) =>
                queryClient.fetchQuery(
                    getHistoryQueryOptions({ uuid, start, end, limit }),
                ),
            ),
            ...uuids.map((uuid) =>
                queryClient.fetchQuery(getUsernameQueryOptions(uuid)),
            ),
        ]).catch((e: unknown) => {
            // TODO: Report error
            console.error(e);
        });
    },
    // https://tanstack.com/router/v1/docs/framework/react/guide/search-params
    validateSearch: zodValidator(historyCompareSearchSchema),
});
