import type { Persister } from "@tanstack/react-query-persist-client";

export const noopPersister: Persister = {
    persistClient: () => Promise.resolve(),
    restoreClient: () => Promise.resolve(undefined),
    removeClient: () => Promise.resolve(),
};
