import { QueryClient } from "@tanstack/react-query";
import type { PersistedClient, Persister } from "@tanstack/react-query-persist-client";
import { get, set, del } from "idb-keyval";

export const maxAge = 1000 * 60 * 60 * 24 * 21; // 21 days

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
