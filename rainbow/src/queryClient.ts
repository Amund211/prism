import { QueryClient } from "@tanstack/react-query";
import { createAsyncStoragePersister } from "@tanstack/query-async-storage-persister";
import superjson from "superjson";

export const maxAge = 1000 * 60 * 60 * 24 * 21; // 21 days

export const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            gcTime: maxAge,
        },
    },
});

export const persister = createAsyncStoragePersister({
    storage: localStorage,
    serialize: superjson.stringify,
    deserialize: superjson.parse,
});
