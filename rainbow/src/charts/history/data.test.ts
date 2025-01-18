import test from "node:test";
import { clusterChartData } from "./data.ts";
import assert from "node:assert";

await test("clusterChartData", async (t) => {
    const now = new Date(2024, 1, 1, 0, 0, 0, 0).getTime();

    const second = 1000;
    const minute = 60 * second;
    const hour = 60 * minute;
    const day = 24 * hour;

    const cases = [
        {
            name: "empty",
            input: [],
            output: [],
        },
        {
            name: "single",
            input: [now],
            output: [now],
        },
        {
            name: "all duplicates",
            input: [now, now, now],
            output: [now, now, now],
        },
        {
            name: "times within 1%",
            input: [now - 2 * hour, now, now + 10 * minute, now + day],
            output: [
                now - 2 * hour,
                now + 10 * minute,
                now + 10 * minute,
                now + day,
            ],
        },
        {
            name: "times within 1m",
            input: [
                now - 1 * second,
                now,
                now + 10 * second,
                now + 20 * second,
                now + 30 * second,
                now + 40 * second,
                now + 50 * second,
                now + minute,
                now + 10 * minute,
            ],
            output: [
                now - 1 * second,
                now + minute,
                now + minute,
                now + minute,
                now + minute,
                now + minute,
                now + minute,
                now + minute,
                now + 10 * minute,
            ],
        },
        {
            name: "multiple clusters within 1m",
            input: [
                now - 1 * second,
                now,
                now + 10 * second,
                now + 20 * second,
                now + 30 * second,
                now + 40 * second,
                now + 50 * second,
                now + minute,
                now + 3 * minute,
                now + 3 * minute + 17 * second,
                now + 3 * minute + 19 * second,
                now + 3 * minute + 28 * second,
                now + 3 * minute + 39 * second,
                now + 3 * minute + 50 * second,
                now + 3 * minute + 59 * second,
                now + 4 * minute + 10 * second,
                now + 4 * minute + 17 * second,
                now + 4 * minute + 19 * second,
                now + 10 * minute,
            ],
            output: [
                now - 1 * second,
                now + minute,
                now + minute,
                now + minute,
                now + minute,
                now + minute,
                now + minute,
                now + minute,
                // We cluster from the end, taking the last entry as the new queriedAt
                now + 3 * minute + 17 * second,
                now + 3 * minute + 17 * second,
                now + 4 * minute + 19 * second,
                now + 4 * minute + 19 * second,
                now + 4 * minute + 19 * second,
                now + 4 * minute + 19 * second,
                now + 4 * minute + 19 * second,
                now + 4 * minute + 19 * second,
                now + 4 * minute + 19 * second,
                now + 4 * minute + 19 * second,
                now + 10 * minute,
            ],
        },
        {
            name: "clusters are not chained -> some clusters remain",
            input: [
                now,
                now + 0.5 * minute,
                now + 1.0 * minute,
                now + 1.5 * minute,
                now + 2.0 * minute,
                now + 2.5 * minute,
                now + 3.0 * minute,
                now + 3.5 * minute,
                now + 4.0 * minute,
                now + 4.5 * minute,
                now + 5.0 * minute,
                now + 5.5 * minute,
                now + 6.0 * minute,
                now + 6.5 * minute,
                now + 7.0 * minute,
            ],
            output: [
                // These cluster in threes because we do <= threshold and not < threshold
                // In practice this does not matter because queriedAt has ms precision
                now + 1.0 * minute,
                now + 1.0 * minute,
                now + 1.0 * minute,
                now + 2.5 * minute,
                now + 2.5 * minute,
                now + 2.5 * minute,
                now + 4.0 * minute,
                now + 4.0 * minute,
                now + 4.0 * minute,
                now + 5.5 * minute,
                now + 5.5 * minute,
                now + 5.5 * minute,
                now + 7.0 * minute,
                now + 7.0 * minute,
                now + 7.0 * minute,
            ],
        },
    ] as const;

    for (const { name, input, output } of cases) {
        await t.test(name, () => {
            const result = clusterChartData(
                input.map((queriedAt) => ({ queriedAt })),
            ).map((entry) => entry.queriedAt);

            assert.deepStrictEqual(result, output, `input ${input.toString()}`);
        });
    }
});
