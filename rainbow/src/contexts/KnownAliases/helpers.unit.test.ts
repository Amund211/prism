import { test, expect, describe } from "vitest";

import { parseStoredAliases, stringifyKnownAliases } from "./helpers.ts";
import type { KnownAliases } from "./helpers.ts";

describe("parse + stringify round trip", () => {
    const cases: { name: string; aliases: KnownAliases }[] = [
        {
            name: "empty",
            aliases: {},
        },
        {
            name: "single user - single alias",
            aliases: {
                "123e4567-e89b-12d3-a456-426614174000": [
                    {
                        username: "PlayerOne",
                        lastResolved: new Date("2024-01-01T00:00:00Z"),
                    },
                ],
            },
        },
        {
            name: "single user - multiple aliases",
            aliases: {
                "123e4567-e89b-12d3-a456-426614174000": [
                    {
                        username: "PlayerOne",
                        lastResolved: new Date("2024-01-01T00:00:00Z"),
                    },
                    {
                        username: "PlayerUno",
                        lastResolved: new Date("2024-03-01T00:00:00Z"),
                    },
                    {
                        username: "Player1",
                        lastResolved: new Date("2024-05-01T00:00:00Z"),
                    },
                ],
            },
        },
        {
            name: "multiple users",
            aliases: {
                "123e4567-e89b-12d3-a456-426614174000": [
                    {
                        username: "PlayerOne",
                        lastResolved: new Date("2024-01-01T00:00:00Z"),
                    },
                    {
                        username: "PlayerUno",
                        lastResolved: new Date("2024-03-01T00:00:00Z"),
                    },
                    {
                        username: "Player1",
                        lastResolved: new Date("2024-05-01T00:00:00Z"),
                    },
                ],
                "123e4567-e89b-12d3-a456-426614174001": [
                    {
                        username: "PlayerTwo",
                        lastResolved: new Date("2024-02-01T00:00:00Z"),
                    },
                ],
                "123e4567-e89b-12d3-a456-426614174002": [
                    {
                        username: "PlayerThree",
                        lastResolved: new Date("2024-03-01T00:00:00Z"),
                    },
                    {
                        username: "PlayerTres",
                        lastResolved: new Date("2024-04-01T00:00:00Z"),
                    },
                ],
            },
        },
    ];

    for (const c of cases) {
        test(c.name, () => {
            expect(parseStoredAliases(stringifyKnownAliases(c.aliases))).toStrictEqual(
                c.aliases,
            );
        });
    }
});
