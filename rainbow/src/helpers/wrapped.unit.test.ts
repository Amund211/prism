import { describe, test, expect } from "vitest";
import { computeWrappedYear } from "./wrapped.ts";

describe(computeWrappedYear, () => {
    const cases = [
        { date: new Date("2025-01-01"), expected: 2024 },
        { date: new Date("2025-05-01"), expected: 2024 },
        { date: new Date("2025-09-30"), expected: 2024 },
        { date: new Date("2025-10-31"), expected: 2024 },
        { date: new Date("2025-11-30"), expected: 2024 },
        { date: new Date("2025-12-01"), expected: 2025 },
        { date: new Date("2025-12-15"), expected: 2025 },
        { date: new Date("2025-12-31"), expected: 2025 },
        { date: new Date("2026-01-01"), expected: 2025 },
        { date: new Date("2026-04-01"), expected: 2025 },
        { date: new Date("2026-08-01"), expected: 2025 },
        { date: new Date("2026-11-30"), expected: 2025 },
        { date: new Date("2026-12-01"), expected: 2026 },
    ];
    for (const { date, expected } of cases) {
        test(`date: ${date.toISOString()}`, () => {
            const result = computeWrappedYear(date);
            expect(result).toBe(expected);
        });
    }
});
