import { test, expect, describe } from "vitest";

import { computeWrappedYear } from "#helpers/wrapped.ts";

import { makeWrappedSearchSchema } from "./wrappedSearch.ts";

// Pin "now" so the current wrapped year is deterministic. In December the
// current calendar year is the active wrapped year, giving us a range
// [2025, 2026] to exercise both bounds.
const NOW = new Date("2026-12-15T12:00:00.000Z");
const currentWrappedYear = computeWrappedYear(NOW); // 2026
const wrappedSearchSchema = makeWrappedSearchSchema(() => NOW);

describe("wrappedSearchSchema validation", () => {
    test("no params -> defaults to the current wrapped year", () => {
        const result = wrappedSearchSchema.parse({});
        expect(result).toStrictEqual({ year: currentWrappedYear });
    });

    test("valid year within range", () => {
        const result = wrappedSearchSchema.parse({ year: 2025 });
        expect(result).toStrictEqual({ year: 2025 });
    });

    test("year at the current-wrapped-year upper bound is valid", () => {
        const result = wrappedSearchSchema.parse({ year: currentWrappedYear });
        expect(result).toStrictEqual({ year: currentWrappedYear });
    });

    test("invalid year -> fallback to current wrapped year", () => {
        const result = wrappedSearchSchema.parse({ year: "not-a-number" });
        expect(result.year).toBe(currentWrappedYear);
    });

    test("year below the minimum -> fallback to current wrapped year", () => {
        const result = wrappedSearchSchema.parse({ year: 1999 });
        expect(result.year).toBe(currentWrappedYear);
    });

    test("year above the upper bound -> fallback to current wrapped year", () => {
        const result = wrappedSearchSchema.parse({ year: currentWrappedYear + 1 });
        expect(result.year).toBe(currentWrappedYear);
    });
});
