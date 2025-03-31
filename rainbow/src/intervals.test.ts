import test from "node:test";
import assert from "node:assert";

import {
    endOfDay,
    endOfLastDay,
    endOfLastMonth,
    endOfLastWeek,
    endOfMonth,
    endOfWeek,
    timeIntervalsFromDefinition,
} from "#intervals.ts";

await test("getTimeIntervals", async (t) => {
    await t.test("contained", async (t) => {
        const cases = [
            {
                date: new Date(2024, 1, 14, 17, 15, 0),
                expected: {
                    day: {
                        start: new Date(2024, 1, 14, 0, 0, 0, 0),
                        end: new Date(2024, 1, 14, 23, 59, 59, 999),
                    },
                    week: {
                        start: new Date(2024, 1, 12, 0, 0, 0, 0),
                        end: new Date(2024, 1, 18, 23, 59, 59, 999),
                    },
                    month: {
                        start: new Date(2024, 1, 1, 0, 0, 0, 0),
                        end: new Date(2024, 1, 29, 23, 59, 59, 999),
                    },
                },
            },
            {
                date: new Date(2025, 2, 31, 18, 16, 0),
                expected: {
                    day: {
                        start: new Date(2025, 2, 31, 0, 0, 0, 0),
                        end: new Date(2025, 2, 31, 23, 59, 59, 999),
                    },
                    week: {
                        start: new Date(2025, 2, 31, 0, 0, 0, 0),
                        end: new Date(2025, 3, 6, 23, 59, 59, 999),
                    },
                    month: {
                        start: new Date(2025, 2, 1, 0, 0, 0, 0),
                        end: new Date(2025, 2, 31, 23, 59, 59, 999),
                    },
                },
            },
        ];
        for (const { date, expected } of cases) {
            await t.test(date.toISOString(), () => {
                const { day, week, month } = timeIntervalsFromDefinition({
                    type: "contained",
                    date,
                });

                assert.strictEqual(
                    day.start.toISOString(),
                    expected.day.start.toISOString(),
                    "day start",
                );
                assert.strictEqual(
                    day.end.toISOString(),
                    expected.day.end.toISOString(),
                    "day end",
                );

                assert.strictEqual(
                    week.start.toISOString(),
                    expected.week.start.toISOString(),
                    "week start",
                );
                assert.strictEqual(
                    week.end.toISOString(),
                    expected.week.end.toISOString(),
                    "week end",
                );

                assert.strictEqual(
                    month.start.toISOString(),
                    expected.month.start.toISOString(),
                    "month start",
                );
                assert.strictEqual(
                    month.end.toISOString(),
                    expected.month.end.toISOString(),
                    "month end",
                );
            });
        }
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

        assert.strictEqual(
            month.start.toISOString(),
            new Date(2024, 0, 16, 0, 0, 0, 0).toISOString(),
        );
        assert.strictEqual(month.end.toISOString(), end.toISOString());
    });
});

await test("time helpers", async (t) => {
    await t.test("endOfDay", async (t) => {
        const cases = [
            {
                date: new Date(2024, 1, 14, 0, 0, 0),
                expected: new Date(2024, 1, 14, 23, 59, 59, 999),
            },
            {
                date: new Date(2024, 1, 14, 17, 15, 0),
                expected: new Date(2024, 1, 14, 23, 59, 59, 999),
            },
            {
                date: new Date(2024, 1, 14, 23, 59, 59, 999),
                expected: new Date(2024, 1, 14, 23, 59, 59, 999),
            },
            {
                date: new Date(2024, 1, 1, 0, 0, 0),
                expected: new Date(2024, 1, 1, 23, 59, 59, 999),
            },
            {
                date: new Date(2024, 1, 1, 0, 0, 0),
                expected: new Date(2024, 1, 1, 23, 59, 59, 999),
            },
        ];
        for (const { date, expected } of cases) {
            await t.test(date.toISOString(), () => {
                assert.strictEqual(
                    endOfDay(date).toISOString(),
                    expected.toISOString(),
                );
            });
        }
    });

    await t.test("endOfWeek", async (t) => {
        const cases = [
            ...new Array(7).fill(null).map((_, i) => ({
                // All days in the week point to the same end of last week
                date: new Date(2024, 1, 12 + i, 17, 15, 0),
                expected: new Date(2024, 1, 18, 23, 59, 59, 999),
            })),
            ...new Array(7).fill(null).map((_, i) => ({
                // All days in the week point to the same end of last week
                date: new Date(2024, 0, 1 + i, 0, 0, 0),
                expected: new Date(2024, 0, 7, 23, 59, 59, 999),
            })),
        ];
        for (const { date, expected } of cases) {
            await t.test(date.toISOString(), () => {
                assert.strictEqual(
                    endOfWeek(date).toISOString(),
                    expected.toISOString(),
                );
            });
        }
    });

    await t.test("endOfMonth", async (t) => {
        const cases = [
            {
                date: new Date(2024, 0, 1, 0, 0, 0),
                expected: new Date(2024, 0, 31, 23, 59, 59, 999),
            },
            {
                date: new Date(2024, 0, 14, 17, 15, 0),
                expected: new Date(2024, 0, 31, 23, 59, 59, 999),
            },
            {
                date: new Date(2024, 0, 29, 23, 59, 59, 999),
                expected: new Date(2024, 0, 31, 23, 59, 59, 999),
            },
            {
                date: new Date(2023, 11, 1, 0, 0, 0),
                expected: new Date(2023, 11, 31, 23, 59, 59, 999),
            },
            {
                date: new Date(2023, 11, 31, 23, 40, 0),
                expected: new Date(2023, 11, 31, 23, 59, 59, 999),
            },
            {
                date: new Date(2025, 1, 27, 18, 40, 0),
                expected: new Date(2025, 1, 28, 23, 59, 59, 999),
            },
            {
                date: new Date(2025, 1, 11, 23, 40, 0),
                expected: new Date(2025, 1, 28, 23, 59, 59, 999),
            },
            {
                date: new Date(2025, 2, 31, 18, 16, 0),
                expected: new Date(2025, 2, 31, 23, 59, 59, 999),
            },
        ];
        for (const { date, expected } of cases) {
            await t.test(date.toISOString(), () => {
                assert.strictEqual(
                    endOfMonth(date).toISOString(),
                    expected.toISOString(),
                );
            });
        }
    });

    await t.test("endOfLastDay", async (t) => {
        const cases = [
            {
                date: new Date(2024, 1, 14, 0, 0, 0),
                expected: new Date(2024, 1, 13, 23, 59, 59, 999),
            },
            {
                date: new Date(2024, 1, 14, 17, 15, 0),
                expected: new Date(2024, 1, 13, 23, 59, 59, 999),
            },
            {
                date: new Date(2024, 1, 14, 23, 59, 59, 999),
                expected: new Date(2024, 1, 13, 23, 59, 59, 999),
            },
            {
                date: new Date(2024, 1, 1, 0, 0, 0),
                expected: new Date(2024, 0, 31, 23, 59, 59, 999),
            },
            {
                date: new Date(2024, 0, 1, 0, 0, 0),
                expected: new Date(2023, 11, 31, 23, 59, 59, 999),
            },
        ];
        for (const { date, expected } of cases) {
            await t.test(date.toISOString(), () => {
                assert.strictEqual(
                    endOfLastDay(date).toISOString(),
                    expected.toISOString(),
                );
            });
        }
    });

    await t.test("endOfLastWeek", async (t) => {
        const cases = [
            ...new Array(7).fill(null).map((_, i) => ({
                // All days in the week point to the same end of last week
                date: new Date(2024, 1, 12 + i, 17, 15, 0),
                expected: new Date(2024, 1, 11, 23, 59, 59, 999),
            })),
            ...new Array(7).fill(null).map((_, i) => ({
                // All days in the week point to the same end of last week
                date: new Date(2024, 0, 1 + i, 0, 0, 0),
                expected: new Date(2023, 11, 31, 23, 59, 59, 999),
            })),
        ];
        for (const { date, expected } of cases) {
            await t.test(date.toISOString(), () => {
                assert.strictEqual(
                    endOfLastWeek(date).toISOString(),
                    expected.toISOString(),
                );
            });
        }
    });

    await t.test("endOfLastMonth", async (t) => {
        const cases = [
            {
                date: new Date(2024, 1, 1, 0, 0, 0),
                expected: new Date(2024, 0, 31, 23, 59, 59, 999),
            },
            {
                date: new Date(2024, 1, 14, 17, 15, 0),
                expected: new Date(2024, 0, 31, 23, 59, 59, 999),
            },
            {
                date: new Date(2024, 1, 29, 23, 59, 59, 999),
                expected: new Date(2024, 0, 31, 23, 59, 59, 999),
            },
            {
                date: new Date(2024, 0, 1, 0, 0, 0),
                expected: new Date(2023, 11, 31, 23, 59, 59, 999),
            },
            {
                date: new Date(2024, 0, 31, 23, 40, 0),
                expected: new Date(2023, 11, 31, 23, 59, 59, 999),
            },
            {
                date: new Date(2025, 2, 29, 18, 40, 0),
                expected: new Date(2025, 1, 28, 23, 59, 59, 999),
            },
            {
                date: new Date(2025, 2, 31, 23, 40, 0),
                expected: new Date(2025, 1, 28, 23, 59, 59, 999),
            },
        ];
        for (const { date, expected } of cases) {
            await t.test(date.toISOString(), () => {
                assert.strictEqual(
                    endOfLastMonth(date).toISOString(),
                    expected.toISOString(),
                );
            });
        }
    });
});
