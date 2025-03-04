import test from "node:test";
import assert from "node:assert";

import { timeIntervalsFromDefinition } from "#intervals.ts";

await test("getTimeIntervals", async (t) => {
    await t.test("contained", () => {
        const { day, week, month } = timeIntervalsFromDefinition({
            type: "contained",
            date: new Date(2024, 1, 14, 17, 15, 0),
        });

        assert.strictEqual(
            day.start.toISOString(),
            new Date(2024, 1, 14, 0, 0, 0, 0).toISOString(),
        );
        assert.strictEqual(
            day.end.toISOString(),
            new Date(2024, 1, 14, 23, 59, 59, 999).toISOString(),
        );

        assert.strictEqual(
            week.start.toISOString(),
            new Date(2024, 1, 12, 0, 0, 0, 0).toISOString(),
        );
        assert.strictEqual(
            week.end.toISOString(),
            new Date(2024, 1, 18, 23, 59, 59, 999).toISOString(),
        );

        assert.strictEqual(
            month.start.toISOString(),
            new Date(2024, 1, 1, 0, 0, 0, 0).toISOString(),
        );
        assert.strictEqual(
            month.end.toISOString(),
            new Date(2024, 1, 29, 23, 59, 59, 999).toISOString(),
        );
    });

    await t.test("until", () => {
        const { day, week, month } = timeIntervalsFromDefinition({
            type: "until",
            date: new Date(2024, 1, 14, 17, 15, 0),
        });

        // With last x days, all intervals stop at the end of the current date
        const end = new Date(2024, 1, 14, 23, 59, 59, 999);

        assert.strictEqual(
            day.start.toISOString(),
            new Date(2024, 1, 14, 0, 0, 0, 0).toISOString(),
        );
        assert.strictEqual(day.end.toISOString(), end.toISOString());

        assert.strictEqual(
            week.start.toISOString(),
            new Date(2024, 1, 8, 0, 0, 0, 0).toISOString(),
        );
        assert.strictEqual(week.end.toISOString(), end.toISOString());

        // 29 days in February 2024
        assert.strictEqual(
            month.start.toISOString(),
            new Date(2024, 0, 17, 0, 0, 0, 0).toISOString(),
        );
        assert.strictEqual(month.end.toISOString(), end.toISOString());
    });
});
