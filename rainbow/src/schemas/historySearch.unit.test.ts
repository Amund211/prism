import { test, expect, describe } from "vitest";
import { ALL_GAMEMODE_KEYS, ALL_STAT_KEYS } from "#stats/keys.ts";
import { historyExploreSearchSchema } from "./historySearch.ts";

const defaultStart = new Date();
defaultStart.setHours(0, 0, 0, 0);
const defaultEnd = new Date();
defaultEnd.setHours(23, 59, 59, 999);

describe("historyExploreSearchSchema validation", () => {
    test("no params -> all defaults", () => {
        const result = historyExploreSearchSchema.parse({});
        expect(result).toStrictEqual({
            uuids: [],
            start: defaultStart,
            end: defaultEnd,
            limit: 50,
            stats: ["fkdr"],
            gamemodes: ["overall"],
            variantSelection: "session",
        });
    });

    test("valid custom values", () => {
        const result = historyExploreSearchSchema.parse({
            uuids: ["069a79f4-44e5-4726-a5be-fca90e000bdf"],
            start: "2025-11-10T23:00:00.000Z",
            end: "2025-11-19T22:59:59.999Z",
            limit: 25,
            stats: ["wins", "losses"],
            gamemodes: ["solo", "doubles"],
            variantSelection: "overall",
        });
        expect(result).toStrictEqual({
            uuids: ["069a79f4-44e5-4726-a5be-fca90e000bdf"],
            start: new Date("2025-11-10T23:00:00.000Z"),
            end: new Date("2025-11-19T22:59:59.999Z"),
            limit: 25,
            stats: ["wins", "losses"],
            gamemodes: ["solo", "doubles"],
            variantSelection: "overall",
        });
    });

    test("invalid uuids -> fallback to empty array", () => {
        const result = historyExploreSearchSchema.parse({
            uuids: "not-an-array",
        });
        expect(result.uuids).toStrictEqual([]);
    });

    test("invalid start date -> fallback to default", () => {
        const result = historyExploreSearchSchema.parse({
            start: "invalid-date",
        });
        // Was struggling with equality on the dates here. Converting to time
        expect(result.start.getTime()).toBe(defaultStart.getTime());
    });

    test("invalid end date -> fallback to default", () => {
        const result = historyExploreSearchSchema.parse({
            end: "invalid-date",
        });
        // Was struggling with equality on the dates here. Converting to time
        expect(result.end.getTime()).toBe(defaultEnd.getTime());
    });

    test("invalid limit -> fallback to default", () => {
        const result = historyExploreSearchSchema.parse({
            limit: "invalid",
        });
        expect(result.limit).toBe(50);
    });

    test("limit too low -> fallback to default", () => {
        const result = historyExploreSearchSchema.parse({
            limit: 0,
        });
        expect(result.limit).toBe(50);
    });

    test("limit too high -> fallback to default", () => {
        const result = historyExploreSearchSchema.parse({
            limit: 100,
        });
        expect(result.limit).toBe(50);
    });

    test("limit within range", () => {
        const result = historyExploreSearchSchema.parse({
            limit: 25,
        });
        expect(result.limit).toBe(25);
    });

    test("invalid stats -> fallback to default", () => {
        const result = historyExploreSearchSchema.parse({
            stats: "invalid",
        });
        expect(result.stats).toStrictEqual(["fkdr"]);
    });

    test("stats array with invalid values -> fallback to default", () => {
        const result = historyExploreSearchSchema.parse({
            stats: ["invalid1", "invalid2"],
        });
        expect(result.stats).toStrictEqual(["fkdr"]);
    });

    test("invalid gamemodes -> fallback to default", () => {
        const result = historyExploreSearchSchema.parse({
            gamemodes: "invalid",
        });
        expect(result.gamemodes).toStrictEqual(["overall"]);
    });

    test("gamemodes array with invalid values -> fallback to default", () => {
        const result = historyExploreSearchSchema.parse({
            gamemodes: ["invalid1", "invalid2"],
        });
        expect(result.gamemodes).toStrictEqual(["overall"]);
    });

    test("invalid variantSelection -> fallback to default", () => {
        const result = historyExploreSearchSchema.parse({
            variantSelection: "invalid",
        });
        expect(result.variantSelection).toBe("session");
    });

    test("date coercion understands simple date strings", () => {
        // NOTE: These should be UTC dates with timezone in production
        const result = historyExploreSearchSchema.parse({
            start: "2024-03-15",
            end: "2024-03-20",
        });

        expect(result.start.getFullYear()).toBe(2024);
        expect(result.start.getMonth()).toBe(2);
        expect(result.start.getDate()).toBe(15);

        expect(result.end.getFullYear()).toBe(2024);
        expect(result.end.getMonth()).toBe(2);
        expect(result.end.getDate()).toBe(20);
    });

    test("date coercion understands timestamps", () => {
        // NOTE: Don't expect this to be used
        const startTimestamp = new Date(2024, 5, 10).getTime();
        const endTimestamp = new Date(2024, 5, 20).getTime();
        const result = historyExploreSearchSchema.parse({
            start: startTimestamp,
            end: endTimestamp,
        });

        expect(result.start.getFullYear()).toBe(2024);
        expect(result.start.getMonth()).toBe(5);
        expect(result.start.getDate()).toBe(10);

        expect(result.end.getFullYear()).toBe(2024);
        expect(result.end.getMonth()).toBe(5);
        expect(result.end.getDate()).toBe(20);
    });

    test("multiple UUIDs", () => {
        const uuids = [
            "069a79f4-44e5-4726-a5be-fca90e000bdf",
            "12345678-1234-1234-1234-123456789012",
        ];
        const result = historyExploreSearchSchema.parse({
            uuids,
        });
        expect(result.uuids).toStrictEqual(uuids);
    });

    test("all valid stat values", () => {
        const result = historyExploreSearchSchema.parse({
            stats: [...ALL_STAT_KEYS],
        });
        expect(result.stats).toStrictEqual([...ALL_STAT_KEYS]);
    });

    test("all valid gamemode values", () => {
        const result = historyExploreSearchSchema.parse({
            gamemodes: [...ALL_GAMEMODE_KEYS],
        });
        expect(result.gamemodes).toStrictEqual([...ALL_GAMEMODE_KEYS]);
    });

    test("mixed valid and invalid params", () => {
        const result = historyExploreSearchSchema.parse({
            uuids: ["069a79f4-44e5-4726-a5be-fca90e000bdf"],
            start: "invalid-date",
            end: "2024-12-31",
            limit: 200,
            stats: ["wins"],
            gamemodes: "invalid",
            variantSelection: "both",
        });
        expect(result).toStrictEqual({
            uuids: ["069a79f4-44e5-4726-a5be-fca90e000bdf"], // Valid
            start: defaultStart, // Invalid, fallback to default
            end: new Date("2024-12-31"), // Valid
            limit: 50, // Invalid, fallback to default
            stats: ["wins"], // Valid
            gamemodes: ["overall"], // Invalid, fallback to default
            variantSelection: "both", // Valid
        });
    });

    test("empty arrays are valid", () => {
        const result = historyExploreSearchSchema.parse({
            uuids: [],
            stats: [],
            gamemodes: [],
        });
        expect(result.uuids).toStrictEqual([]);
        expect(result.stats).toStrictEqual([]);
        expect(result.gamemodes).toStrictEqual([]);
    });

    test("all three variantSelection values", () => {
        for (const variant of ["session", "overall", "both"] as const) {
            const result = historyExploreSearchSchema.parse({
                variantSelection: variant,
            });
            expect(result.variantSelection).toBe(variant);
        }
    });
});
