import { createFileRoute } from "@tanstack/react-router";
import { queryClient } from "#queryClient.ts";
import { getHistoryQueryOptions } from "#queries/history.ts";
import { fallback } from "@tanstack/zod-adapter";
import { z } from "zod";
import { ALL_GAMEMODE_KEYS, ALL_STAT_KEYS } from "#stats/keys.ts";
import { getUsernameQueryOptions } from "#queries/username.ts";

const defaultStart = new Date();
defaultStart.setHours(0, 0, 0, 0);
const defaultEnd = new Date();
defaultEnd.setHours(23, 59, 59, 999);

const historyCompareSearchSchema = z.object({
    // TODO: Read "preferred user" from local storage or similar
    uuids: fallback(z.array(z.string()).readonly(), []),
    start: fallback(z.coerce.date(), defaultStart),
    end: fallback(z.coerce.date(), defaultEnd),
    limit: fallback(z.number().int().min(1).max(50), 50),
    stats: fallback(z.enum(ALL_STAT_KEYS).array().readonly(), ["fkdr"]),
    gamemodes: fallback(z.enum(ALL_GAMEMODE_KEYS).array().readonly(), [
        "overall",
    ]),
    variantSelection: fallback(
        z.enum(["session", "overall", "both"]),
        "session",
    ),
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
    validateSearch: historyCompareSearchSchema,
});
