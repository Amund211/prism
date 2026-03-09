import { test, expect, describe } from "vitest";
import { ALL_GAMEMODE_KEYS, ALL_STAT_KEYS } from "#stats/keys.ts";
import { sessionSearchSchema } from "./sessionSearch.ts";

// Helper to get the expected default tracking start (start of day 1 year ago)
const getDefaultTrackingStart = () => {
    const date = new Date();
    date.setFullYear(date.getFullYear() - 1);
    date.setHours(0, 0, 0, 0);
    return date;
};

describe("sessionSearchSchema validation", () => {
    test("no params -> all defaults", () => {
        const result = sessionSearchSchema.parse({});
        const expectedDefault = getDefaultTrackingStart();
        expect(result).toStrictEqual({
            gamemode: "overall",
            stat: "fkdr",
            variantSelection: "both",
            sessionTableMode: "total",
            showExtrapolatedSessions: false,
            timeIntervalDefinition: {
                type: "contained",
            },
            trackingStart: expectedDefault,
        });
    });

    test("valid custom values", () => {
        const result = sessionSearchSchema.parse({
            gamemode: "solo",
            stat: "wins",
            variantSelection: "session",
            sessionTableMode: "rate",
            showExtrapolatedSessions: true,
            timeIntervalDefinition: {
                type: "until",
                date: "2025-11-03T22:59:59.999Z",
            },
            trackingStart: "2020-01-01T00:00:00.000Z",
        });
        expect(result).toStrictEqual({
            gamemode: "solo",
            stat: "wins",
            variantSelection: "session",
            sessionTableMode: "rate",
            showExtrapolatedSessions: true,
            timeIntervalDefinition: {
                type: "until",
                date: new Date("2025-11-03T22:59:59.999Z"),
            },
            trackingStart: new Date("2020-01-01T00:00:00.000Z"),
        });
    });

    test("invalid gamemode -> fallback to default", () => {
        const result = sessionSearchSchema.parse({
            gamemode: "invalid",
        });
        expect(result.gamemode).toBe("overall");
    });

    test("invalid stat -> fallback to default", () => {
        const result = sessionSearchSchema.parse({
            stat: "invalid",
        });
        expect(result.stat).toBe("fkdr");
    });

    test("invalid variantSelection -> fallback to default", () => {
        const result = sessionSearchSchema.parse({
            variantSelection: "invalid",
        });
        expect(result.variantSelection).toBe("both");
    });

    test("invalid sessionTableMode -> fallback to default", () => {
        const result = sessionSearchSchema.parse({
            sessionTableMode: "invalid",
        });
        expect(result.sessionTableMode).toBe("total");
    });

    test("invalid showExtrapolatedSessions -> fallback to default", () => {
        const result = sessionSearchSchema.parse({
            showExtrapolatedSessions: "invalid",
        });
        expect(result.showExtrapolatedSessions).toBe(false);
    });

    test("invalid timeIntervalDefinition -> fallback to default", () => {
        const result = sessionSearchSchema.parse({
            timeIntervalDefinition: "invalid",
        });
        expect(result.timeIntervalDefinition).toStrictEqual({
            type: "contained",
        });
    });

    test("invalid trackingStart -> fallback to default", () => {
        const result = sessionSearchSchema.parse({
            trackingStart: "invalid",
        });
        const expectedDefault = getDefaultTrackingStart();
        expect(result.trackingStart).toStrictEqual(expectedDefault);
    });

    test("default trackingStart is 1 year ago from now (same date)", () => {
        const result = sessionSearchSchema.parse({});
        const now = new Date();
        const expectedDate = new Date();
        expectedDate.setFullYear(expectedDate.getFullYear() - 1);
        expectedDate.setHours(0, 0, 0, 0);

        // Verify the year is exactly 1 year less
        expect(result.trackingStart.getFullYear()).toBe(now.getFullYear() - 1);

        // Verify the month and day are the same
        // NOTE: This test will fail on leap years when run on Feb 29
        // because setFullYear on Feb 29 of a leap year going back to a non-leap year
        // will result in March 1 instead of Feb 28
        expect(result.trackingStart.getMonth()).toBe(expectedDate.getMonth());
        expect(result.trackingStart.getDate()).toBe(expectedDate.getDate());

        // Also verify it's at the start of the day (midnight)
        expect(result.trackingStart.getHours()).toBe(0);
        expect(result.trackingStart.getMinutes()).toBe(0);
        expect(result.trackingStart.getSeconds()).toBe(0);
        expect(result.trackingStart.getMilliseconds()).toBe(0);
    });

    test("date coercion understands simple date strings", () => {
        // NOTE: These should be UTC dates with timezone in production
        const result = sessionSearchSchema.parse({
            trackingStart: "2024-01-15",
        });

        expect(result.trackingStart.getFullYear()).toBe(2024);
        expect(result.trackingStart.getMonth()).toBe(0);
        expect(result.trackingStart.getDate()).toBe(15);
    });

    test("date coercion understands timestamps", () => {
        // NOTE: Don't expect this to be used
        const timestamp = new Date(2024, 0, 15).getTime();
        const result = sessionSearchSchema.parse({
            trackingStart: timestamp,
        });

        expect(result.trackingStart.getFullYear()).toBe(2024);
        expect(result.trackingStart.getMonth()).toBe(0);
        expect(result.trackingStart.getDate()).toBe(15);
    });

    test("timeIntervalDefinition with contained type and date", () => {
        const result = sessionSearchSchema.parse({
            timeIntervalDefinition: {
                type: "contained",
                date: "2024-06-15",
            },
        });
        expect(result.timeIntervalDefinition.type).toBe("contained");
        const { date: containedDate } = result.timeIntervalDefinition;
        if (containedDate === undefined) {
            expect.unreachable("date should be defined");
        }
        expect(containedDate).toBeInstanceOf(Date);
        expect(containedDate.getFullYear()).toBe(2024);
        expect(containedDate.getMonth()).toBe(5);
    });

    test("timeIntervalDefinition with until type and date", () => {
        const result = sessionSearchSchema.parse({
            timeIntervalDefinition: {
                type: "until",
                date: "2024-12-25",
            },
        });
        expect(result.timeIntervalDefinition.type).toBe("until");
        const { date: untilDate } = result.timeIntervalDefinition;
        if (untilDate === undefined) {
            expect.unreachable("date should be defined");
        }
        expect(untilDate).toBeInstanceOf(Date);
        expect(untilDate.getFullYear()).toBe(2024);
        expect(untilDate.getMonth()).toBe(11);
    });

    test("timeIntervalDefinition contained with invalid date -> fallback to undefined", () => {
        const result = sessionSearchSchema.parse({
            timeIntervalDefinition: {
                type: "contained",
                date: "invalid-date",
            },
        });
        expect(result.timeIntervalDefinition.type).toBe("contained");
        expect(result.timeIntervalDefinition.date).toBe(undefined);
    });

    test("timeIntervalDefinition until with invalid date -> fallback to undefined", () => {
        const result = sessionSearchSchema.parse({
            timeIntervalDefinition: {
                type: "until",
                date: "invalid-date",
            },
        });
        expect(result.timeIntervalDefinition.type).toBe("until");
        expect(result.timeIntervalDefinition.date).toBe(undefined);
    });

    test("all valid gamemode values", () => {
        for (const gamemode of ALL_GAMEMODE_KEYS) {
            const result = sessionSearchSchema.parse({ gamemode });
            expect(result.gamemode).toBe(gamemode);
        }
    });

    test("all valid stat values", () => {
        for (const stat of ALL_STAT_KEYS) {
            const result = sessionSearchSchema.parse({ stat });
            expect(result.stat).toBe(stat);
        }
    });

    test("mixed valid and invalid params", () => {
        const result = sessionSearchSchema.parse({
            gamemode: "invalid",
            stat: "wins",
            variantSelection: "invalid",
            sessionTableMode: "rate",
            showExtrapolatedSessions: "invalid",
        });
        const expectedDefault = getDefaultTrackingStart();
        expect(result.gamemode).toBe("overall"); // fallback
        expect(result.stat).toBe("wins"); // valid
        expect(result.variantSelection).toBe("both"); // fallback
        expect(result.sessionTableMode).toBe("rate"); // valid
        expect(result.showExtrapolatedSessions).toBe(false); // fallback
        expect(result).toStrictEqual({
            gamemode: "overall", // fallback
            stat: "wins", // valid
            variantSelection: "both", // fallback
            sessionTableMode: "rate", // valid
            showExtrapolatedSessions: false, // fallback
            timeIntervalDefinition: {
                // fallback
                type: "contained",
            },
            trackingStart: expectedDefault, // fallback
        });
    });
});
