import { test, expect, describe } from "vitest";

import {
    endOfDay,
    endOfLastDay,
    endOfLastMonth,
    endOfLastWeek,
    endOfMonth,
    endOfWeek,
    timeIntervalsFromDefinition,
} from "#intervals.ts";

describe("getTimeIntervals", () => {
    describe("contained", () => {
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
            test(date.toISOString(), () => {
                const { day, week, month } = timeIntervalsFromDefinition({
                    type: "contained",
                    date,
                });

                expect(day.start.toISOString(), "day start").toBe(
                    expected.day.start.toISOString(),
                );
                expect(day.end.toISOString(), "day end").toBe(
                    expected.day.end.toISOString(),
                );

                expect(week.start.toISOString(), "week start").toBe(
                    expected.week.start.toISOString(),
                );
                expect(week.end.toISOString(), "week end").toBe(
                    expected.week.end.toISOString(),
                );

                expect(month.start.toISOString(), "month start").toBe(
                    expected.month.start.toISOString(),
                );
                expect(month.end.toISOString(), "month end").toBe(
                    expected.month.end.toISOString(),
                );
            });
        }
    });

    test("until", () => {
        const { day, week, month } = timeIntervalsFromDefinition({
            type: "until",
            date: new Date(2024, 1, 14, 17, 15, 0),
        });

        // With last x days, all intervals stop at the end of the current date
        const end = new Date(2024, 1, 14, 23, 59, 59, 999);

        expect(day.start.toISOString()).toBe(
            new Date(2024, 1, 14, 0, 0, 0, 0).toISOString(),
        );
        expect(day.end.toISOString()).toBe(end.toISOString());

        expect(week.start.toISOString()).toBe(
            new Date(2024, 1, 8, 0, 0, 0, 0).toISOString(),
        );
        expect(week.end.toISOString()).toBe(end.toISOString());

        expect(month.start.toISOString()).toBe(
            new Date(2024, 0, 16, 0, 0, 0, 0).toISOString(),
        );
        expect(month.end.toISOString()).toBe(end.toISOString());
    });
});

describe("time helpers", () => {
    describe("endOfDay", () => {
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
            test(date.toISOString(), () => {
                expect(endOfDay(date).toISOString()).toBe(expected.toISOString());
            });
        }
    });

    describe("endOfWeek", () => {
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
            test(date.toISOString(), () => {
                expect(endOfWeek(date).toISOString()).toBe(expected.toISOString());
            });
        }
    });

    describe("endOfMonth", () => {
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
            test(date.toISOString(), () => {
                expect(endOfMonth(date).toISOString()).toBe(expected.toISOString());
            });
        }
    });

    describe("endOfLastDay", () => {
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
            test(date.toISOString(), () => {
                expect(endOfLastDay(date).toISOString()).toBe(expected.toISOString());
            });
        }
    });

    describe("endOfLastWeek", () => {
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
            test(date.toISOString(), () => {
                expect(endOfLastWeek(date).toISOString()).toBe(expected.toISOString());
            });
        }
    });

    describe("endOfLastMonth", () => {
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
            test(date.toISOString(), () => {
                expect(endOfLastMonth(date).toISOString()).toBe(expected.toISOString());
            });
        }
    });
});
