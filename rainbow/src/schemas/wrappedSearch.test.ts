import test from "node:test";
import assert from "node:assert";
import { wrappedSearchSchema } from "./wrappedSearch.ts";
import { getWrappedYear } from "#helpers/wrapped.ts";

await test("wrappedSearchSchema validation", async (t) => {
    await t.test("no params -> all defaults", () => {
        const result = wrappedSearchSchema.parse({});
        assert.deepStrictEqual(result, {
            year: getWrappedYear(),
        });
    });

    await t.test("valid custom values", () => {
        const result = wrappedSearchSchema.parse({
            year: 2025,
        });
        assert.deepStrictEqual(result, {
            year: 2025,
        });
    });
});
