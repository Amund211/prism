import { get, set, del } from "idb-keyval";
import {
    type PersistedClient,
    type Persister,
} from "@tanstack/react-query-persist-client";
import { QueryClient } from "@tanstack/react-query";

export const maxAge = 1000 * 60 * 60 * 24 * 21; // 21 days

export const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            gcTime: maxAge,
        },
    },
});

// From: https://tanstack.com/query/latest/docs/framework/react/plugins/persistQueryClient
// https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API
function createIDBPersister(idbValidKey: IDBValidKey = "reactQuery") {
    return {
        persistClient: async (client: PersistedClient) => {
            await set(idbValidKey, client);
        },
        restoreClient: async () => {
            return await get<PersistedClient>(idbValidKey);
        },
        removeClient: async () => {
            await del(idbValidKey);
        },
    } satisfies Persister;
}

export const persister = createIDBPersister();
