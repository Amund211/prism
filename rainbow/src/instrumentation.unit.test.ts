import { describe, expect, test } from "vitest";

import { redactBreadcrumb, redactEvent } from "./instrumentation.ts";

describe(redactEvent, () => {
    // An event sent before the callback page removes the fragment.
    test("redacts a result token in the request url", () => {
        expect(
            redactEvent({
                type: undefined,
                request: { url: "https://x.test/auth/microsoft#result=flresult_abc" },
            }),
        ).toStrictEqual({
            type: undefined,
            request: {
                url: "https://x.test/auth/microsoft#result=flresult_<redacted>",
            },
        });
    });

    test("leaves an event without a request alone", () => {
        const event = { type: undefined, message: "hi" };

        expect(redactEvent(event)).toBe(event);
    });
});

describe(redactBreadcrumb, () => {
    // Removing the callback fragment is a replaceState, which Sentry records
    // with the old URL.
    test("redacts a result token in a navigation breadcrumb", () => {
        expect(
            redactBreadcrumb({
                category: "navigation",
                data: {
                    from: "/auth/microsoft#result=flresult_abc.def",
                    to: "/auth/microsoft",
                },
            }),
        ).toStrictEqual({
            category: "navigation",
            data: {
                from: "/auth/microsoft#result=flresult_<redacted>",
                to: "/auth/microsoft",
            },
        });
    });

    test("leaves other breadcrumbs alone", () => {
        const breadcrumb = { category: "console", message: "flresult_abc" };

        expect(redactBreadcrumb(breadcrumb)).toBe(breadcrumb);
    });
});
