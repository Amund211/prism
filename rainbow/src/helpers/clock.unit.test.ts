import { afterAll, beforeAll, describe, expect, test, vi } from "vitest";

import { nextBoundary, truncate } from "./clock.ts";
import type { Precision } from "./clock.ts";

const inTimezone = (tz: string, fn: () => void) => {
    describe(tz, () => {
        beforeAll(() => {
            vi.stubEnv("TZ", tz);
        });

        afterAll(() => {
            vi.unstubAllEnvs();
        });
        fn();
    });
};

interface Case {
    readonly name: string;
    readonly at: string;
    readonly precision: Precision;
    readonly expected: string;
}

const runCases = (
    fn: (ms: number, precision: Precision) => number,
    cases: readonly Case[],
) => {
    for (const { name, at, precision, expected } of cases) {
        test(name, () => {
            const result = fn(new Date(at).getTime(), precision);
            expect(new Date(result).toISOString()).toBe(expected);
        });
    }
};

inTimezone("UTC", () => {
    describe(truncate, () => {
        runCases(truncate, [
            {
                name: "second",
                at: "2026-01-31T23:59:30.500Z",
                precision: "second",
                expected: "2026-01-31T23:59:30.000Z",
            },
            {
                name: "minute",
                at: "2026-01-31T23:59:30.500Z",
                precision: "minute",
                expected: "2026-01-31T23:59:00.000Z",
            },
            {
                name: "hour",
                at: "2026-01-31T23:59:30.500Z",
                precision: "hour",
                expected: "2026-01-31T23:00:00.000Z",
            },
            {
                name: "day",
                at: "2026-01-31T23:59:30.500Z",
                precision: "day",
                expected: "2026-01-31T00:00:00.000Z",
            },
            {
                name: "month",
                at: "2026-01-31T23:59:30.500Z",
                precision: "month",
                expected: "2026-01-01T00:00:00.000Z",
            },
            {
                name: "year",
                at: "2026-05-31T23:59:30.500Z",
                precision: "year",
                expected: "2026-01-01T00:00:00.000Z",
            },
        ]);
    });

    describe(nextBoundary, () => {
        runCases(nextBoundary, [
            {
                name: "minute",
                at: "2026-01-31T23:59:30.500Z",
                precision: "minute",
                expected: "2026-02-01T00:00:00.000Z",
            },
            {
                name: "month",
                at: "2026-12-31T12:00:00.000Z",
                precision: "month",
                expected: "2027-01-01T00:00:00.000Z",
            },
            {
                name: "exactly on a boundary",
                at: "2026-01-31T23:59:00.000Z",
                precision: "minute",
                expected: "2026-02-01T00:00:00.000Z",
            },
        ]);
    });
});

// Clocks go back from 03:00 CEST to 02:00 CET on 2026-10-25
inTimezone("Europe/Oslo", () => {
    describe(truncate, () => {
        runCases(truncate, [
            {
                name: "minute in the first 02:30 (CEST)",
                at: "2026-10-25T00:30:45.000Z",
                precision: "minute",
                expected: "2026-10-25T00:30:00.000Z",
            },
            {
                name: "minute in the repeated 02:30 (CET)",
                at: "2026-10-25T01:30:45.000Z",
                precision: "minute",
                expected: "2026-10-25T01:30:00.000Z",
            },
            {
                name: "hour in the first 02:00 (CEST)",
                at: "2026-10-25T00:30:45.000Z",
                precision: "hour",
                expected: "2026-10-25T00:00:00.000Z",
            },
            {
                name: "hour in the repeated 02:00 (CET)",
                at: "2026-10-25T01:30:45.000Z",
                precision: "hour",
                expected: "2026-10-25T01:00:00.000Z",
            },
            {
                name: "day in the first 02:30 (CEST)",
                at: "2026-10-25T00:30:45.000Z",
                precision: "day",
                expected: "2026-10-24T22:00:00.000Z",
            },
            {
                name: "day in the repeated 02:30 (CET)",
                at: "2026-10-25T01:30:45.000Z",
                precision: "day",
                expected: "2026-10-24T22:00:00.000Z",
            },
            {
                name: "day on the change day",
                at: "2026-10-25T12:00:00.000Z",
                precision: "day",
                expected: "2026-10-24T22:00:00.000Z",
            },
        ]);
    });

    describe(nextBoundary, () => {
        runCases(nextBoundary, [
            {
                name: "minute in the first 02:30 (CEST)",
                at: "2026-10-25T00:30:45.000Z",
                precision: "minute",
                expected: "2026-10-25T00:31:00.000Z",
            },
            {
                name: "minute in the repeated 02:30 (CET)",
                at: "2026-10-25T01:30:45.000Z",
                precision: "minute",
                expected: "2026-10-25T01:31:00.000Z",
            },
            {
                name: "hour from the first 02:00 (CEST) into the repeated 02:00 (CET)",
                at: "2026-10-25T00:30:45.000Z",
                precision: "hour",
                expected: "2026-10-25T01:00:00.000Z",
            },
            {
                name: "hour from the repeated 02:00 (CET) into 03:00 (CET)",
                at: "2026-10-25T01:30:45.000Z",
                precision: "hour",
                expected: "2026-10-25T02:00:00.000Z",
            },
            {
                name: "day across the change",
                at: "2026-10-25T12:00:00.000Z",
                precision: "day",
                expected: "2026-10-25T23:00:00.000Z",
            },
        ]);
    });
});

// Clocks skip from 00:00 to 01:00 on 2026-09-06
inTimezone("America/Santiago", () => {
    describe(truncate, () => {
        runCases(truncate, [
            {
                name: "day starting at 01:00",
                at: "2026-09-06T15:00:00.000Z",
                precision: "day",
                expected: "2026-09-06T04:00:00.000Z",
            },
        ]);
    });

    describe(nextBoundary, () => {
        runCases(nextBoundary, [
            {
                name: "day into the skipped midnight",
                at: "2026-09-05T16:00:00.000Z",
                precision: "day",
                expected: "2026-09-06T04:00:00.000Z",
            },
            {
                name: "day after the skipped midnight",
                at: "2026-09-06T15:00:00.000Z",
                precision: "day",
                expected: "2026-09-07T03:00:00.000Z",
            },
        ]);
    });
});

// UTC+05:30, so local hours start at :30 UTC
inTimezone("Asia/Kolkata", () => {
    describe(truncate, () => {
        runCases(truncate, [
            {
                name: "hour",
                at: "2026-01-01T10:00:00.000Z",
                precision: "hour",
                expected: "2026-01-01T09:30:00.000Z",
            },
        ]);
    });

    describe(nextBoundary, () => {
        runCases(nextBoundary, [
            {
                name: "hour",
                at: "2026-01-01T10:00:00.000Z",
                precision: "hour",
                expected: "2026-01-01T10:30:00.000Z",
            },
        ]);
    });
});
