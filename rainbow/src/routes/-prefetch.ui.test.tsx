import { QueryClient } from "@tanstack/react-query";
import { describe, expect } from "vitest";

import { stringifyPlayerVisits } from "#contexts/PlayerVisits/helpers.ts";
import { timeIntervalsFromDefinition } from "#intervals.ts";
import { USERS } from "#mocks/data.ts";
import { getHistoryQueryOptions } from "#queries/history.ts";
import { getSessionAtQueryOptions } from "#queries/sessionAt.ts";
import { getSessionsQueryOptions } from "#queries/sessions.ts";
import { getUsernameQueryOptions } from "#queries/username.ts";
import { Route as indexRoute } from "#routes/index.tsx";
import { Route as sessionRoute } from "#routes/session/$uuid.tsx";
import { Route as detailRoute } from "#routes/session/$uuid_.detail.tsx";
import { mswTest } from "#test/msw-test.ts";

// The loaders are invoked directly, so the query keys asserted here can only
// come from the loader — not from the route's components.
interface RouteWithLoader {
    readonly options: {
        readonly loaderDeps?: unknown;
        readonly loader?: unknown;
    };
}

type LoaderDeps = (ctx: { readonly search: unknown }) => unknown;
type Loader = (ctx: {
    readonly params: unknown;
    readonly deps: unknown;
    readonly context: { readonly queryClient: QueryClient };
}) => unknown;

// Query keys are nested arrays, so compare them as sorted JSON to get an exact
// set comparison with a readable diff.
const asComparableKeys = (queryKeys: readonly unknown[]): string[] =>
    queryKeys.map((queryKey) => JSON.stringify(queryKey)).toSorted();

/**
 * Run a route's `loaderDeps` and `loader` against a fresh query client, and
 * return the query keys the loader put in the cache.
 */
const runLoader = async (
    route: RouteWithLoader,
    { params, search }: { readonly params?: unknown; readonly search: unknown },
): Promise<string[]> => {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    const { loaderDeps, loader } = route.options;
    expect(loader).toBeDefined();

    const deps = loaderDeps === undefined ? {} : (loaderDeps as LoaderDeps)({ search });
    await (loader as Loader)({ params, deps, context: { queryClient } });

    return asComparableKeys(
        queryClient
            .getQueryCache()
            .getAll()
            .map((query) => query.queryKey),
    );
};

const { uuid } = USERS.player1;
// A fixed "until" date makes the derived day/week/month intervals deterministic.
const date = new Date("2025-11-03T22:00:00.000Z");
const timeIntervalDefinition = { type: "until", date } as const;

describe("Route loader prefetching", () => {
    mswTest("the session page prefetches everything its cards read", async () => {
        const trackingStart = new Date("2024-11-03T00:00:00.000Z");
        const keys = await runLoader(sessionRoute, {
            params: { uuid },
            search: { timeIntervalDefinition, trackingStart },
        });

        const { day, week, month } =
            timeIntervalsFromDefinition(timeIntervalDefinition);
        const expected: unknown[] = [getUsernameQueryOptions(uuid).queryKey];
        for (const { start, end } of [day, week, month]) {
            // limit 2 for the stat cards, limit 100 for their sparklines.
            expected.push(
                getHistoryQueryOptions({ uuid, start, end, limit: 2 }).queryKey,
                getHistoryQueryOptions({ uuid, start, end, limit: 100 }).queryKey,
            );
        }
        expected.push(
            // The milestone-progress card.
            getHistoryQueryOptions({
                uuid,
                start: trackingStart,
                end: day.end,
                limit: 2,
            }).queryKey,
            // The sessions table.
            getSessionsQueryOptions({ uuid, start: month.start, end: month.end })
                .queryKey,
        );

        expect(keys).toStrictEqual(asComparableKeys(expected));
    });

    mswTest("the session detail page prefetches the session and username", async () => {
        const keys = await runLoader(detailRoute, {
            params: { uuid },
            search: { date },
        });

        expect(keys).toStrictEqual(
            asComparableKeys([
                getSessionAtQueryOptions({ uuid, time: date }).queryKey,
                getUsernameQueryOptions(uuid).queryKey,
            ]),
        );
    });

    mswTest("the home page prefetches the favorites' usernames", async () => {
        localStorage.setItem(
            "playerVisits",
            stringifyPlayerVisits({
                [uuid]: { visitedCount: 1, lastVisited: new Date() },
                [USERS.player2.uuid]: { visitedCount: 1, lastVisited: new Date() },
            }),
        );

        const keys = await runLoader(indexRoute, { search: {} });

        expect(keys).toStrictEqual(
            asComparableKeys([
                getUsernameQueryOptions(uuid).queryKey,
                getUsernameQueryOptions(USERS.player2.uuid).queryKey,
            ]),
        );
    });
});
