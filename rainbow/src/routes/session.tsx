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
    ),
    trackingStart: fallback(z.coerce.date().optional(), undefined).transform(
        (value) => {
            if (value === undefined) {
                return new Date(1970, 0, 1);
            }
            return value;
        },
    ),
    gamemode: fallback(z.enum(ALL_GAMEMODE_KEYS), "overall"),
    stat: fallback(z.enum(ALL_STAT_KEYS), "fkdr"),
    variantSelection: fallback(z.enum(["session", "overall", "both"]), "both"),
});

export const Route = createFileRoute("/session")({
    loaderDeps: ({ search: { uuid, timeInterval, trackingStart } }) => {
        const intervalWithCurrentDate =
            timeInterval.type === "current"
                ? { ...timeInterval, currentDate: new Date() }
                : timeInterval;

        const timeIntervals = getTimeIntervals(intervalWithCurrentDate);
        return {
            uuid,
            timeInterval,
            // Try to end the interval in the past so we don't need to re-fetch
            trackingInterval: {
                start: trackingStart,
                end: timeIntervals.day.start,
            },
            timeIntervals,
        };
    },
    loader: ({ deps: { uuid, timeIntervals, trackingInterval } }) => {
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
            queryClient.fetchQuery(
                getHistoryQueryOptions({
                    uuid,
                    ...trackingInterval,
                    limit: 2,
                }),
            ),
            queryClient.fetchQuery(getUsernameQueryOptions(uuid)),
        ]).catch((e: unknown) => {
            // TODO: Report error
            console.error(e);
        });
    },
    validateSearch: sessionSearchSchema,
});
