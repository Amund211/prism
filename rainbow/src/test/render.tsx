import { QueryClient } from "@tanstack/react-query";
import { render } from "vitest-browser-react";

import { App } from "#App.tsx";
import { createAppRouter } from "#createRouter.ts";
import { noopPersister } from "#test/persister.ts";

function createQueryClient() {
    return new QueryClient({
        defaultOptions: {
            queries: { retry: false, gcTime: 0 },
        },
    });
}

/**
 * Render the real app, starting at a specific URL.
 */
export async function renderAppRoute(initialEntry: string) {
    const queryClient = createQueryClient();
    const router = createAppRouter(queryClient);

    globalThis.history.pushState({}, "", initialEntry);

    const screen = await render(
        <App router={router} queryClient={queryClient} persister={noopPersister} />,
    );
    return { screen, queryClient, router };
}
