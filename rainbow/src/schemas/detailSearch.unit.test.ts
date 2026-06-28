import { test, expect, describe } from "vitest";

import { makeDetailSearchSchema } from "./detailSearch.ts";

// Pin "now" so fallbacks are deterministic instead of drifting with the
// wall-clock. Tests assert against this exact instant.
const NOW = new Date("2025-06-15T12:34:56.789Z");
const detailSearchSchema = makeDetailSearchSchema(() => NOW);

describe("detailSearchSchema validation", () => {
    test("valid date string is coerced to a Date", () => {
        const result = detailSearchSchema.parse({
            date: "2025-11-03T22:59:59.999Z",
        });
        expect(result.date).toStrictEqual(new Date("2025-11-03T22:59:59.999Z"));
    });

    test("date coercion understands simple date strings", () => {
        // NOTE: These should be UTC dates with timezone in production
        const result = detailSearchSchema.parse({ date: "2024-01-15" });

        expect(result.date.getFullYear()).toBe(2024);
        expect(result.date.getMonth()).toBe(0);
        expect(result.date.getDate()).toBe(15);
    });

    test("missing date -> falls back to the injected current time", () => {
        const result = detailSearchSchema.parse({});
        expect(result.date).toStrictEqual(NOW);
    });

    test("malformed date -> falls back to the injected current time", () => {
        const result = detailSearchSchema.parse({ date: "not-a-date" });
        expect(result.date).toStrictEqual(NOW);
    });
});
