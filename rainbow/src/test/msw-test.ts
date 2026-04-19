import { test as testBase } from "vitest";

import { worker } from "#mocks/worker.ts";

export const mswTest = testBase.extend({
    worker: [
        // oxlint-disable-next-line no-empty-pattern, react/rules-of-hooks
        async ({}, use) => {
            // Start the worker before the test.
            await worker.start({ onUnhandledRequest: "error", quiet: true });

            // Expose the worker object on the test's context.
            await use(worker);

            // Remove any request handlers added in individual test cases.
            // This prevents them from affecting unrelated tests.
            worker.resetHandlers();

            // Stop the worker after the test.
            worker.stop();
        },
        {
            auto: true,
        },
    ],
});
