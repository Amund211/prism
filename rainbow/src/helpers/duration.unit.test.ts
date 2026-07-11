import { describe, expect, test } from "vitest";

import { formatDuration } from "./duration.ts";

describe(formatDuration, () => {
    const cases: { name: string; ms: number; expected: string }[] = [
        { name: "zero", ms: 0, expected: "0m" },
        { name: "negative clamps to 0m", ms: -5000, expected: "0m" },
        { name: "rounds to the nearest minute", ms: 100_000, expected: "2m" },
        { name: "minutes only", ms: 45 * 60_000, expected: "45m" },
        { name: "hours zero-pad the minutes", ms: 65 * 60_000, expected: "1h 05m" },
        { name: "ninety minutes", ms: 90 * 60_000, expected: "1h 30m" },
        { name: "days and hours", ms: 25 * 60 * 60_000, expected: "1d 1h" },
    ];

    test.each(cases)("$name", ({ ms, expected }) => {
        expect(formatDuration(ms)).toBe(expected);
    });
});
