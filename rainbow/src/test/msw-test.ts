import type { SetupWorker } from "msw/browser";
import { test as testBase } from "vitest";

import { worker } from "#mocks/worker.ts";

export const mswTest = testBase.extend<{
    $file: { worker: SetupWorker };
    $test: { resetHandlers: undefined };
}>({
    // msw 3 throws on a second start(), and stopping between tests races with
    // in-flight requests (mswjs/msw#2706), so start once per file and never stop.
    worker: [
        // oxlint-disable-next-line no-empty-pattern
        async ({}, use) => {
            await worker.start({ onUnhandledFrame: "error", quiet: true });
            await use(worker);
        },
        { scope: "file", auto: true },
    ],
    resetHandlers: [
        async ({ worker: fileWorker }, use) => {
            await use(undefined);

            // Remove any request handlers added in individual test cases.
            // This prevents them from affecting unrelated tests.
            fileWorker.resetHandlers();
        },
        { auto: true },
    ],
});
