import type { QueryClient } from "@tanstack/react-query";
import { createRouter } from "@tanstack/react-router";

import { routeTree } from "./routeTree.gen.ts";

export function createAppRouter(queryClient: QueryClient) {
    return createRouter({
        routeTree,
        defaultPreload: "intent",
        // Defer caching/staleness to TanStack Query so the router doesn't
        // run a competing cache. See https://tkdodo.eu/blog/tan-stack-router-and-query
        defaultPreloadStaleTime: 0,
        context: { queryClient },
    });
}

export type AppRouter = ReturnType<typeof createAppRouter>;

declare module "@tanstack/react-router" {
    interface Register {
        router: AppRouter;
    }
}
