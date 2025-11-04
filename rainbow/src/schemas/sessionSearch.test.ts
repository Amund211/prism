import test from "node:test";
import assert from "node:assert";
import { ALL_GAMEMODE_KEYS, ALL_STAT_KEYS } from "#stats/keys.ts";
import { sessionSearchSchema } from "./sessionSearch.ts";

const defaultTrackingStart = new Date(1970, 0, 1);

await test("sessionSearchSchema validation", async (t) => {
    await t.test("no params -> all defaults", () => {
        const result = sessionSearchSchema.parse({});
        assert.deepStrictEqual(result, {
            gamemode: "overall",
            stat: "fkdr",
            variantSelection: "both",
            sessionTableMode: "total",
            showExtrapolatedSessions: false,
            timeIntervalDefinition: {
                type: "contained",
            },
            trackingStart: defaultTrackingStart,
        });
    });

    await t.test("valid custom values", () => {
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
        assert.deepStrictEqual(result, {
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

    await t.test("invalid gamemode -> fallback to default", () => {
        const result = sessionSearchSchema.parse({
            gamemode: "invalid",
        });
        assert.strictEqual(result.gamemode, "overall");
    });

    await t.test("invalid stat -> fallback to default", () => {
        const result = sessionSearchSchema.parse({
            stat: "invalid",
        });
        assert.strictEqual(result.stat, "fkdr");
    });

    await t.test("invalid variantSelection -> fallback to default", () => {
        const result = sessionSearchSchema.parse({
            variantSelection: "invalid",
        });
        assert.strictEqual(result.variantSelection, "both");
    });

    await t.test("invalid sessionTableMode -> fallback to default", () => {
        const result = sessionSearchSchema.parse({
            sessionTableMode: "invalid",
        });
        assert.strictEqual(result.sessionTableMode, "total");
    });

    await t.test(
        "invalid showExtrapolatedSessions -> fallback to default",
        () => {
            const result = sessionSearchSchema.parse({
                showExtrapolatedSessions: "invalid",
            });
            assert.strictEqual(result.showExtrapolatedSessions, false);
        },
    );

    await t.test(
        "invalid timeIntervalDefinition -> fallback to default",
        () => {
            const result = sessionSearchSchema.parse({
                timeIntervalDefinition: "invalid",
            });
            assert.deepStrictEqual(result.timeIntervalDefinition, {
                type: "contained",
            });
        },
    );

    await t.test("invalid trackingStart -> fallback to default", () => {
        const result = sessionSearchSchema.parse({
            trackingStart: "invalid",
        });
        assert.deepStrictEqual(result.trackingStart, defaultTrackingStart);
    });

    await t.test("date coercion understands simple date strings", () => {
        // NOTE: These should be UTC dates with timezone in production
        const result = sessionSearchSchema.parse({
            trackingStart: "2024-01-15",
        });

        assert.strictEqual(result.trackingStart.getFullYear(), 2024);
        assert.strictEqual(result.trackingStart.getMonth(), 0);
        assert.strictEqual(result.trackingStart.getDate(), 15);
    });

    await t.test("date coercion understands timestamps", () => {
        // NOTE: Don't expect this to be used
        const timestamp = new Date(2024, 0, 15).getTime();
        const result = sessionSearchSchema.parse({
            trackingStart: timestamp,
        });

        assert.strictEqual(result.trackingStart.getFullYear(), 2024);
        assert.strictEqual(result.trackingStart.getMonth(), 0);
        assert.strictEqual(result.trackingStart.getDate(), 15);
    });

    await t.test("timeIntervalDefinition with contained type and date", () => {
        const result = sessionSearchSchema.parse({
            timeIntervalDefinition: {
                type: "contained",
                date: "2024-06-15",
            },
        });
        assert.strictEqual(result.timeIntervalDefinition.type, "contained");
        assert.ok(result.timeIntervalDefinition.date instanceof Date);
        assert.strictEqual(
            result.timeIntervalDefinition.date.getFullYear(),
            2024,
        );
        assert.strictEqual(result.timeIntervalDefinition.date.getMonth(), 5);
    });

    await t.test("timeIntervalDefinition with until type and date", () => {
        const result = sessionSearchSchema.parse({
            timeIntervalDefinition: {
                type: "until",
                date: "2024-12-25",
            },
        });
        assert.strictEqual(result.timeIntervalDefinition.type, "until");
        assert.ok(result.timeIntervalDefinition.date instanceof Date);
        assert.strictEqual(
            result.timeIntervalDefinition.date.getFullYear(),
            2024,
        );
        assert.strictEqual(result.timeIntervalDefinition.date.getMonth(), 11);
    });

    await t.test(
        "timeIntervalDefinition contained with invalid date -> fallback to undefined",
        () => {
            const result = sessionSearchSchema.parse({
                timeIntervalDefinition: {
                    type: "contained",
                    date: "invalid-date",
                },
            });
            assert.strictEqual(result.timeIntervalDefinition.type, "contained");
            assert.strictEqual(result.timeIntervalDefinition.date, undefined);
        },
    );

    await t.test(
        "timeIntervalDefinition until with invalid date -> fallback to undefined",
        () => {
            const result = sessionSearchSchema.parse({
                timeIntervalDefinition: {
                    type: "until",
                    date: "invalid-date",
                },
            });
            assert.strictEqual(result.timeIntervalDefinition.type, "until");
            assert.strictEqual(result.timeIntervalDefinition.date, undefined);
        },
    );

    await t.test("all valid gamemode values", () => {
        for (const gamemode of ALL_GAMEMODE_KEYS) {
            const result = sessionSearchSchema.parse({ gamemode });
            assert.strictEqual(result.gamemode, gamemode);
        }
    });

    await t.test("all valid stat values", () => {
        for (const stat of ALL_STAT_KEYS) {
            const result = sessionSearchSchema.parse({ stat });
            assert.strictEqual(result.stat, stat);
        }
    });

    await t.test("mixed valid and invalid params", () => {
        const result = sessionSearchSchema.parse({
            gamemode: "invalid",
            stat: "wins",
            variantSelection: "invalid",
            sessionTableMode: "rate",
            showExtrapolatedSessions: "invalid",
        });
        assert.strictEqual(result.gamemode, "overall"); // fallback
        assert.strictEqual(result.stat, "wins"); // valid
        assert.strictEqual(result.variantSelection, "both"); // fallback
        assert.strictEqual(result.sessionTableMode, "rate"); // valid
        assert.strictEqual(result.showExtrapolatedSessions, false); // fallback
        assert.deepStrictEqual(result, {
            gamemode: "overall", // fallback
            stat: "wins", // valid
            variantSelection: "both", // fallback
            sessionTableMode: "rate", // valid
            showExtrapolatedSessions: false, // fallback
            timeIntervalDefinition: {
                // fallback
                type: "contained",
            },
            trackingStart: defaultTrackingStart, // fallback
        });
    });
});
