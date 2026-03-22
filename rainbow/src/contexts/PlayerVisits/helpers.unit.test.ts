import { test, expect, describe } from "vitest";
import {
    parseStoredPlayerVisits,
    stringifyPlayerVisits,
    type PlayerVisits,
} from "./helpers.ts";

describe("parse + stringify round trip", () => {
    const cases: { name: string; visits: PlayerVisits }[] = [
        {
            name: "empty",
            visits: {},
        },
        {
            name: "single user",
            visits: {
                "123e4567-e89b-12d3-a456-426614174000": {
                    visitedCount: 5,
                    lastVisited: new Date("2024-01-01T00:00:00Z"),
                },
            },
        },
        {
            name: "multiple users",
            visits: {
                "123e4567-e89b-12d3-a456-426614174000": {
                    visitedCount: 5,
                    lastVisited: new Date("2024-01-01T00:00:00Z"),
                },
                "123e4567-e89b-12d3-a456-426614174001": {
                    visitedCount: 10,
                    lastVisited: new Date("2024-02-01T00:00:00Z"),
                },
                "123e4567-e89b-12d3-a456-426614174002": {
                    visitedCount: 15,
                    lastVisited: new Date("2024-03-01T00:00:00Z"),
                },
            },
        },
    ];

    for (const c of cases) {
        test(c.name, () => {
            expect(
                parseStoredPlayerVisits(stringifyPlayerVisits(c.visits)),
            ).toStrictEqual(c.visits);
        });
    }
});
