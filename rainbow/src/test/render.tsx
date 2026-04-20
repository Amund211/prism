import { render } from "vitest-browser-react";

import { QueryClient } from "@tanstack/react-query";
import { createAppRouter } from "#createRouter.ts";
import { noopPersister } from "#test/persister.ts";
import { App } from "#App.tsx";

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

    window.history.pushState({}, "", initialEntry);

    const screen = await render(
        <App router={router} queryClient={queryClient} persister={noopPersister} />,
    );
    return { screen, queryClient, router };
}
