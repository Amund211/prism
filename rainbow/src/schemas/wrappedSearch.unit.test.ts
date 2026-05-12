import { test, expect, describe } from "vitest";

import { getWrappedYear } from "#helpers/wrapped.ts";

import { wrappedSearchSchema } from "./wrappedSearch.ts";

describe("wrappedSearchSchema validation", () => {
    test("no params -> all defaults", () => {
        const result = wrappedSearchSchema.parse({});
        expect(result).toStrictEqual({
            year: getWrappedYear(),
        });
    });

    test("valid custom values", () => {
        const result = wrappedSearchSchema.parse({
            year: 2025,
        });
        expect(result).toStrictEqual({
            year: 2025,
        });
    });

    test("invalid year -> fallback to default", () => {
        const result = wrappedSearchSchema.parse({
            year: "not-a-number",
        });
        expect(result.year).toBe(getWrappedYear());
    });

    test("year out of range -> fallback to default", () => {
        const result = wrappedSearchSchema.parse({
            year: 1999,
        });
        expect(result.year).toBe(getWrappedYear());
    });
});
