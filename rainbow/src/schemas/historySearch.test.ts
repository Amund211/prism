import test from "node:test";
import assert from "node:assert";
import { ALL_GAMEMODE_KEYS, ALL_STAT_KEYS } from "#stats/keys.ts";
import { historyExploreSearchSchema } from "./historySearch.ts";

const defaultStart = new Date();
defaultStart.setHours(0, 0, 0, 0);
const defaultEnd = new Date();
defaultEnd.setHours(23, 59, 59, 999);

await test("historyExploreSearchSchema validation", async (t) => {
    await t.test("no params -> all defaults", () => {
        const result = historyExploreSearchSchema.parse({});
        assert.deepStrictEqual(result, {
            uuids: [],
            start: defaultStart,
            end: defaultEnd,
            limit: 50,
            stats: ["fkdr"],
            gamemodes: ["overall"],
            variantSelection: "session",
        });
    });

    await t.test("valid custom values", () => {
        const result = historyExploreSearchSchema.parse({
            uuids: ["069a79f4-44e5-4726-a5be-fca90e000bdf"],
            start: "2025-11-10T23:00:00.000Z",
            end: "2025-11-19T22:59:59.999Z",
            limit: 25,
            stats: ["wins", "losses"],
            gamemodes: ["solo", "doubles"],
            variantSelection: "overall",
        });
        assert.deepStrictEqual(result, {
            uuids: ["069a79f4-44e5-4726-a5be-fca90e000bdf"],
            start: new Date("2025-11-10T23:00:00.000Z"),
            end: new Date("2025-11-19T22:59:59.999Z"),
            limit: 25,
            stats: ["wins", "losses"],
            gamemodes: ["solo", "doubles"],
            variantSelection: "overall",
        });
    });

    await t.test("invalid uuids -> fallback to empty array", () => {
        const result = historyExploreSearchSchema.parse({
            uuids: "not-an-array",
        });
        assert.deepStrictEqual(result.uuids, []);
    });

    await t.test("invalid start date -> fallback to default", () => {
        const result = historyExploreSearchSchema.parse({
            start: "invalid-date",
        });
        // Was struggling with equality on the dates here. Converting to time
        assert.strictEqual(result.start.getTime(), defaultStart.getTime());
    });

    await t.test("invalid end date -> fallback to default", () => {
        const result = historyExploreSearchSchema.parse({
            end: "invalid-date",
        });
        // Was struggling with equality on the dates here. Converting to time
        assert.strictEqual(result.end.getTime(), defaultEnd.getTime());
    });

    await t.test("invalid limit -> fallback to default", () => {
        const result = historyExploreSearchSchema.parse({
            limit: "invalid",
        });
        assert.strictEqual(result.limit, 50);
    });

    await t.test("limit too low -> fallback to default", () => {
        const result = historyExploreSearchSchema.parse({
            limit: 0,
        });
        assert.strictEqual(result.limit, 50);
    });

    await t.test("limit too high -> fallback to default", () => {
        const result = historyExploreSearchSchema.parse({
            limit: 100,
        });
        assert.strictEqual(result.limit, 50);
    });

    await t.test("limit within range", () => {
        const result = historyExploreSearchSchema.parse({
            limit: 25,
        });
        assert.strictEqual(result.limit, 25);
    });

    await t.test("invalid stats -> fallback to default", () => {
        const result = historyExploreSearchSchema.parse({
            stats: "invalid",
        });
        assert.deepStrictEqual(result.stats, ["fkdr"]);
    });

    await t.test(
        "stats array with invalid values -> fallback to default",
        () => {
            const result = historyExploreSearchSchema.parse({
                stats: ["invalid1", "invalid2"],
            });
            assert.deepStrictEqual(result.stats, ["fkdr"]);
        },
    );

    await t.test("invalid gamemodes -> fallback to default", () => {
        const result = historyExploreSearchSchema.parse({
            gamemodes: "invalid",
        });
        assert.deepStrictEqual(result.gamemodes, ["overall"]);
    });

    await t.test(
        "gamemodes array with invalid values -> fallback to default",
        () => {
            const result = historyExploreSearchSchema.parse({
                gamemodes: ["invalid1", "invalid2"],
            });
            assert.deepStrictEqual(result.gamemodes, ["overall"]);
        },
    );

    await t.test("invalid variantSelection -> fallback to default", () => {
        const result = historyExploreSearchSchema.parse({
            variantSelection: "invalid",
        });
        assert.strictEqual(result.variantSelection, "session");
    });

    await t.test("date coercion understands simple date strings", () => {
        // NOTE: These should be UTC dates with timezone in production
        const result = historyExploreSearchSchema.parse({
            start: "2024-03-15",
            end: "2024-03-20",
        });

        assert.strictEqual(result.start.getFullYear(), 2024);
        assert.strictEqual(result.start.getMonth(), 2);
        assert.strictEqual(result.start.getDate(), 15);

        assert.strictEqual(result.end.getFullYear(), 2024);
        assert.strictEqual(result.end.getMonth(), 2);
        assert.strictEqual(result.end.getDate(), 20);
    });

    await t.test("date coercion understands timestamps", () => {
        // NOTE: Don't expect this to be used
        const startTimestamp = new Date(2024, 5, 10).getTime();
        const endTimestamp = new Date(2024, 5, 20).getTime();
        const result = historyExploreSearchSchema.parse({
            start: startTimestamp,
            end: endTimestamp,
        });

        assert.strictEqual(result.start.getFullYear(), 2024);
        assert.strictEqual(result.start.getMonth(), 5);
        assert.strictEqual(result.start.getDate(), 10);

        assert.strictEqual(result.end.getFullYear(), 2024);
        assert.strictEqual(result.end.getMonth(), 5);
        assert.strictEqual(result.end.getDate(), 20);
    });

    await t.test("multiple UUIDs", () => {
        const uuids = [
            "069a79f4-44e5-4726-a5be-fca90e000bdf",
            "12345678-1234-1234-1234-123456789012",
        ];
        const result = historyExploreSearchSchema.parse({
            uuids,
        });
        assert.deepStrictEqual(result.uuids, uuids);
    });

    await t.test("all valid stat values", () => {
        const result = historyExploreSearchSchema.parse({
            stats: [...ALL_STAT_KEYS],
        });
        assert.deepStrictEqual(result.stats, [...ALL_STAT_KEYS]);
    });

    await t.test("all valid gamemode values", () => {
        const result = historyExploreSearchSchema.parse({
            gamemodes: [...ALL_GAMEMODE_KEYS],
        });
        assert.deepStrictEqual(result.gamemodes, [...ALL_GAMEMODE_KEYS]);
    });

    await t.test("mixed valid and invalid params", () => {
        const result = historyExploreSearchSchema.parse({
            uuids: ["069a79f4-44e5-4726-a5be-fca90e000bdf"],
            start: "invalid-date",
            end: "2024-12-31",
            limit: 200,
            stats: ["wins"],
            gamemodes: "invalid",
            variantSelection: "both",
        });
        assert.deepStrictEqual(result, {
            uuids: ["069a79f4-44e5-4726-a5be-fca90e000bdf"], // Valid
            start: defaultStart, // Invalid, fallback to default
            end: new Date("2024-12-31"), // Valid
            limit: 50, // Invalid, fallback to default
            stats: ["wins"], // Valid
            gamemodes: ["overall"], // Invalid, fallback to default
            variantSelection: "both", // Valid
        });
    });

    await t.test("empty arrays are valid", () => {
        const result = historyExploreSearchSchema.parse({
            uuids: [],
            stats: [],
            gamemodes: [],
        });
        assert.deepStrictEqual(result.uuids, []);
        assert.deepStrictEqual(result.stats, []);
        assert.deepStrictEqual(result.gamemodes, []);
    });

    await t.test("all three variantSelection values", () => {
        for (const variant of ["session", "overall", "both"] as const) {
            const result = historyExploreSearchSchema.parse({
                variantSelection: variant,
            });
            assert.strictEqual(result.variantSelection, variant);
        }
    });
});
