import { QueryClient, defaultShouldDehydrateQuery } from "@tanstack/react-query";
import type { Query } from "@tanstack/react-query";
import type { PersistedClient, Persister } from "@tanstack/react-query-persist-client";
import { get, set, del } from "idb-keyval";

import { MS_PER_DAY } from "#time.ts";

export const maxAge = MS_PER_DAY * 21; // 21 days

declare module "@tanstack/react-query" {
    interface Register {
        queryMeta: {
            // false keeps the query out of the IndexedDB persister.
            persist?: boolean;
        };
    }
}

/**
 * The persister's dehydrate filter. A query with `meta: { persist: false }`
 * stays in memory only.
 */
// oxlint-disable-next-line typescript/prefer-readonly-parameter-types -- dehydrateOptions passes a mutable Query
export const shouldPersistQuery = (query: Query): boolean =>
    defaultShouldDehydrateQuery(query) && query.meta?.persist !== false;

export function createQueryClient() {
    return new QueryClient({
        defaultOptions: {
            queries: {
                gcTime: maxAge,
            },
        },
    });
}

// From: https://tanstack.com/query/latest/docs/framework/react/plugins/persistQueryClient
// https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API
export function createIDBPersister(idbValidKey: IDBValidKey = "reactQuery") {
    return {
        persistClient: async (client: PersistedClient) => {
            await set(idbValidKey, client);
        },
        restoreClient: async () => {
            return get<PersistedClient>(idbValidKey);
        },
        removeClient: async () => {
            await del(idbValidKey);
        },
    } satisfies Persister;
}
