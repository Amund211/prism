import type { Persister } from "@tanstack/react-query-persist-client";

export const noopPersister: Persister = {
    // oxlint-disable-next-line typescript/promise-function-async
    persistClient: () => Promise.resolve(),
    // oxlint-disable-next-line typescript/promise-function-async
    restoreClient: () => Promise.resolve(undefined),
    // oxlint-disable-next-line typescript/promise-function-async
    removeClient: () => Promise.resolve(),
};
