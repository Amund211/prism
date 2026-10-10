import { QueryClient, dehydrate, queryOptions } from "@tanstack/react-query";
import { describe, expect, test } from "vitest";

import { shouldPersistQuery } from "#queryClient.ts";

describe(shouldPersistQuery, () => {
    const persistedKeys = async (persist?: boolean) => {
        const client = new QueryClient();
        await client.query(
            queryOptions({
                queryKey: ["thing"],
                // oxlint-disable-next-line typescript/promise-function-async
                queryFn: () => Promise.resolve(1),
                ...(persist === undefined ? {} : { meta: { persist } }),
            }),
        );
        return dehydrate(client, {
            shouldDehydrateQuery: shouldPersistQuery,
        }).queries.map((query) => query.queryKey);
    };

    test("persists a successful query", async () => {
        await expect(persistedKeys()).resolves.toStrictEqual([["thing"]]);
    });

    test("skips a query with meta.persist false", async () => {
        await expect(persistedKeys(false)).resolves.toStrictEqual([]);
    });
});
