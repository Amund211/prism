import { createFileRoute } from "@tanstack/react-router";
import { queryClient } from "#queryClient.ts";
import { getHistoryQueryOptions } from "#queries/history.ts";
import { zodValidator } from "@tanstack/zod-adapter";
import { z } from "zod";
import { getUsernameQueryOptions } from "#queries/username.ts";
import { getTimeIntervals } from "#intervals.ts";

const sessionSearchSchema = z.object({
    // TODO: Read "preferred user" from local storage or similar
    uuid: z.string().catch(""),
    timeInterval: z
        .union([
            z.object({ type: z.literal("current") }),
            z.object({
                type: z.literal("lastXDays"),
                end: z.coerce.date().optional().catch(undefined),
            }),
        ])
        .catch({ type: "current" })
        .transform((value) => {
            if (value.type === "current") {
                return { ...value, currentDate: new Date() };
            }
            return value;
        }),
});

export const Route = createFileRoute("/session")({
    loaderDeps: ({ search: { uuid, timeInterval } }) => ({
        uuid,
        timeInterval,
    }),
    loader: ({ deps: { uuid, timeInterval } }) => {
        const { day, week, month } = getTimeIntervals(timeInterval);
        // TODO: Rate limiting
        Promise.all([
            [day, week, month].map(({ start, end }) =>
                queryClient.fetchQuery(
                    getHistoryQueryOptions({ uuid, start, end, limit: 2 }),
                ),
            ),
            queryClient.fetchQuery(getUsernameQueryOptions(uuid)),
        ]).catch((e: unknown) => {
            // TODO: Report error
            console.error(e);
        });
    },
    // https://tanstack.com/router/v1/docs/framework/react/guide/search-params
    validateSearch: zodValidator(sessionSearchSchema),
});
