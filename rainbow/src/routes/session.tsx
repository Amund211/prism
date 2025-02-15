import { createFileRoute } from "@tanstack/react-router";
import { queryClient } from "#queryClient.ts";
import { getHistoryQueryOptions } from "#queries/history.ts";
import { fallback } from "@tanstack/zod-adapter";
import { z } from "zod";
import { getUsernameQueryOptions } from "#queries/username.ts";
import { getTimeIntervals } from "#intervals.ts";
import { ALL_GAMEMODE_KEYS, ALL_STAT_KEYS } from "#stats/keys.ts";

const sessionSearchSchema = z.object({
    // TODO: Read "preferred user" from local storage or similar
    uuid: fallback(z.string(), ""),
    timeInterval: fallback(
        z.union([
            z.object({ type: z.literal("current") }),
            z.object({
                type: z.literal("lastXDays"),
                end: fallback(z.coerce.date().optional(), undefined),
            }),
        ]),
        { type: "current" },
    ).transform((value) => {
        if (value.type === "current") {
            return { ...value, currentDate: new Date() };
        }
        return value;
    }),
    gamemode: fallback(z.enum(ALL_GAMEMODE_KEYS), "overall"),
    stat: fallback(z.enum(ALL_STAT_KEYS), "fkdr"),
    variantSelection: fallback(z.enum(["session", "overall", "both"]), "both"),
});

export const Route = createFileRoute("/session")({
    loaderDeps: ({ search: { uuid, timeInterval } }) => {
        const timeIntervals = getTimeIntervals(timeInterval);
        return { uuid, timeInterval, timeIntervals };
    },
    loader: ({ deps: { uuid, timeIntervals } }) => {
        const { day, week, month } = timeIntervals;
        // TODO: Rate limiting
        Promise.all([
            [day, week, month].map(({ start, end }) =>
                Promise.all([
                    queryClient.fetchQuery(
                        getHistoryQueryOptions({ uuid, start, end, limit: 2 }),
                    ),
                    queryClient.fetchQuery(
                        getHistoryQueryOptions({
                            uuid,
                            start,
                            end,
                            limit: 100,
                        }),
                    ),
                ]),
            ),
            queryClient.fetchQuery(getUsernameQueryOptions(uuid)),
        ]).catch((e: unknown) => {
            // TODO: Report error
            console.error(e);
        });
    },
    validateSearch: sessionSearchSchema,
});
