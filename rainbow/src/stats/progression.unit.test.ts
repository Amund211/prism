import { test, expect, describe } from "vitest";

import type { History } from "#queries/history.ts";
import type { PlayerDataPIT, StatsPIT } from "#queries/playerdata.ts";

import { ALL_GAMEMODE_KEYS } from "./keys.ts";
import type { GamemodeKey, StatKey } from "./keys.ts";
import {
    computeStatProgression,
    ERR_NO_DATA,
    ERR_TRACKING_STARTED,
    findSmallestPositiveCubicRoot,
} from "./progression.ts";
import { bedwarsLevelFromExp } from "./stars.ts";

const TEST_UUID = "0123e456-7890-1234-5678-90abcdef1234";

type Mutable<T> = { -readonly [K in keyof T]: T[K] };

class StatsBuilder {
    private readonly stats: Mutable<StatsPIT>;

    public constructor() {
        this.stats = {
            winstreak: null,
            gamesPlayed: 0,
            wins: 0,
            losses: 0,
            bedsBroken: 0,
            bedsLost: 0,
            finalKills: 0,
            finalDeaths: 0,
            kills: 0,
            deaths: 0,
        };
    }

    public withStat(stat: "winstreak", value: number | null): this;
    public withStat(
        stat: Exclude<
            StatKey,
            "winstreak" | "fkdr" | "kdr" | "index" | "stars" | "experience"
        >,
        value: number,
    ): this;
    public withStat(
        stat: Exclude<StatKey, "fkdr" | "kdr" | "index" | "stars" | "experience">,
        value: number | null,
    ): this {
        switch (stat) {
            case "gamesPlayed": {
                if (value === null) throw new Error(`${stat} cannot be null`);
                this.stats.gamesPlayed = value;
                break;
            }
            case "wins": {
                if (value === null) throw new Error(`${stat} cannot be null`);
                this.stats.wins = value;
                break;
            }
            case "losses": {
                if (value === null) throw new Error(`${stat} cannot be null`);
                this.stats.losses = value;
                break;
            }
            case "bedsBroken": {
                if (value === null) throw new Error(`${stat} cannot be null`);
                this.stats.bedsBroken = value;
                break;
            }
            case "bedsLost": {
                if (value === null) throw new Error(`${stat} cannot be null`);
                this.stats.bedsLost = value;
                break;
            }
            case "finalKills": {
                if (value === null) throw new Error(`${stat} cannot be null`);
                this.stats.finalKills = value;
                break;
            }
            case "finalDeaths": {
                if (value === null) throw new Error(`${stat} cannot be null`);
                this.stats.finalDeaths = value;
                break;
            }
            case "kills": {
                if (value === null) throw new Error(`${stat} cannot be null`);
                this.stats.kills = value;
                break;
            }
            case "deaths": {
                if (value === null) throw new Error(`${stat} cannot be null`);
                this.stats.deaths = value;
                break;
            }
            case "winstreak": {
                this.stats.winstreak = value;
                break;
            }
            default: {
                stat satisfies never;
            }
        }
        return this;
    }

    public build(): StatsPIT {
        // Return a copy to prevent mutation
        return { ...this.stats };
    }
}

class PlayerDataBuilder {
    private player: Mutable<PlayerDataPIT>;

    public constructor(uuid: string, queriedAt: Date) {
        const emptyStats: StatsPIT = {
            winstreak: null,
            gamesPlayed: 0,
            wins: 0,
            losses: 0,
            bedsBroken: 0,
            bedsLost: 0,
            finalKills: 0,
            finalDeaths: 0,
            kills: 0,
            deaths: 0,
        };

        this.player = {
            uuid,
            queriedAt,
            experience: 0,
            solo: { ...emptyStats },
            doubles: { ...emptyStats },
            threes: { ...emptyStats },
            fours: { ...emptyStats },
            overall: { ...emptyStats },
        };
    }

    public withExperience(experience: number): this {
        this.player.experience = experience;
        return this;
    }

    public withGamemodeStats(gamemode: GamemodeKey, stats: StatsPIT): this {
        this.player[gamemode] = { ...stats };
        return this;
    }

    public build(): PlayerDataPIT {
        // Return a copy to prevent mutation
        return {
            ...this.player,
            solo: { ...this.player.solo },
            doubles: { ...this.player.doubles },
            threes: { ...this.player.threes },
            fours: { ...this.player.fours },
            overall: { ...this.player.overall },
        };
    }
}

describe("computeStatProgression - error cases", () => {
    const startDate = new Date("2024-01-01T00:00:00Z");
    const endDate = new Date("2024-01-02T00:00:00Z");

    const cases: {
        name: string;
        history: History | undefined;
        reason: string;
    }[] = [
        { name: "undefined history", history: undefined, reason: ERR_NO_DATA },
        { name: "empty history", history: [], reason: ERR_NO_DATA },
        {
            name: "one element history",
            history: [new PlayerDataBuilder(TEST_UUID, startDate).build()],
            reason: ERR_TRACKING_STARTED,
        },
        {
            name: "no progress",
            history: [
                new PlayerDataBuilder(TEST_UUID, startDate)
                    .withGamemodeStats(
                        "overall",
                        new StatsBuilder().withStat("wins", 100).build(),
                    )
                    .build(),
                new PlayerDataBuilder(TEST_UUID, endDate)
                    .withGamemodeStats(
                        "overall",
                        new StatsBuilder().withStat("wins", 100).build(),
                    )
                    .build(),
            ],
            reason: "No progress",
        },
        {
            name: "three element history",
            history: [
                new PlayerDataBuilder(TEST_UUID, startDate)
                    .withGamemodeStats(
                        "overall",
                        new StatsBuilder().withStat("wins", 100).build(),
                    )
                    .build(),
                new PlayerDataBuilder(TEST_UUID, new Date("2024-01-01T12:00:00Z"))
                    .withGamemodeStats(
                        "overall",
                        new StatsBuilder().withStat("wins", 150).build(),
                    )
                    .build(),
                new PlayerDataBuilder(TEST_UUID, endDate)
                    .withGamemodeStats(
                        "overall",
                        new StatsBuilder().withStat("wins", 200).build(),
                    )
                    .build(),
            ],
            reason: "Expected at most 2 data points",
        },
    ];

    for (const c of cases) {
        test(`should return error for ${c.name}`, () => {
            const result = computeStatProgression(
                c.history,
                endDate,
                "wins",
                "overall",
            );
            expect(result).toStrictEqual({
                error: true,
                reason: c.reason,
            });
        });
    }
});

describe("computeStatProgression - linear gamemode stats", () => {
    // Stats that are linear (not fkdr) and gamemode-specific (not stars)
    const linearGamemodeStats = [
        "gamesPlayed",
        "wins",
        "losses",
        "bedsBroken",
        "bedsLost",
        "finalKills",
        "finalDeaths",
        "kills",
        "deaths",
    ] as const;

    const gamemodes = ALL_GAMEMODE_KEYS;

    for (const gamemode of gamemodes) {
        describe(`gamemode: ${gamemode}`, () => {
            for (const stat of linearGamemodeStats) {
                describe(`stat: ${stat}`, () => {
                    test("basic - steady progress", () => {
                        const startDate = new Date("2024-01-01T00:00:00Z");
                        const endDate = new Date("2024-01-11T00:00:00Z"); // 10 days
                        const startBuilder = new PlayerDataBuilder(
                            TEST_UUID,
                            startDate,
                        );
                        const endBuilder = new PlayerDataBuilder(TEST_UUID, endDate);
                        startBuilder.withGamemodeStats(
                            gamemode,
                            new StatsBuilder().withStat(stat, 100).build(),
                        );
                        endBuilder.withGamemodeStats(
                            gamemode,
                            new StatsBuilder().withStat(stat, 200).build(), // +100 in 10 days = 10/day
                        );

                        const history: History = [
                            startBuilder.build(),
                            endBuilder.build(),
                        ];

                        const result = computeStatProgression(
                            history,
                            endDate,
                            stat,
                            gamemode,
                        );

                        if (result.error) {
                            expect.unreachable(
                                `Expected success but got error: ${result.reason}`,
                            );
                        }

                        expect(result).toStrictEqual({
                            stat,
                            endValue: 200,
                            progressPerDay: 10,
                            nextMilestoneValue: 300,
                            daysUntilMilestone: 10,
                            trendingUpward: true,
                            trackingDataTimeInterval: {
                                start: startDate,
                                end: endDate,
                            },
                        });
                    });

                    test("edge case - zero starting value", () => {
                        const startDate = new Date("2024-01-01T00:00:00Z");
                        const endDate = new Date("2024-01-06T00:00:00Z");
                        const startBuilder = new PlayerDataBuilder(
                            TEST_UUID,
                            startDate,
                        );
                        const endBuilder = new PlayerDataBuilder(TEST_UUID, endDate);
                        startBuilder.withGamemodeStats(
                            gamemode,
                            new StatsBuilder().withStat(stat, 0).build(),
                        );
                        endBuilder.withGamemodeStats(
                            gamemode,
                            new StatsBuilder().withStat(stat, 100).build(),
                        );

                        const history: History = [
                            startBuilder.build(),
                            endBuilder.build(),
                        ];

                        const result = computeStatProgression(
                            history,
                            endDate,
                            stat,
                            gamemode,
                        );

                        if (result.error) {
                            expect.unreachable(
                                `Expected success but got error: ${result.reason}`,
                            );
                        }

                        expect(result).toStrictEqual({
                            stat,
                            endValue: 100,
                            progressPerDay: 20,
                            nextMilestoneValue: 200,
                            daysUntilMilestone: 5,
                            trendingUpward: true,
                            trackingDataTimeInterval: {
                                start: startDate,
                                end: endDate,
                            },
                        });
                    });

                    test("edge case - large values", () => {
                        const startDate = new Date("2025-01-01T00:00:00Z");
                        const endDate = new Date("2025-01-21T00:00:00Z");
                        const startBuilder = new PlayerDataBuilder(
                            TEST_UUID,
                            startDate,
                        );
                        const endBuilder = new PlayerDataBuilder(TEST_UUID, endDate);
                        startBuilder.withGamemodeStats(
                            gamemode,
                            new StatsBuilder().withStat(stat, 100_000).build(),
                        );
                        endBuilder.withGamemodeStats(
                            gamemode,
                            new StatsBuilder().withStat(stat, 110_000).build(),
                        );

                        const history: History = [
                            startBuilder.build(),
                            endBuilder.build(),
                        ];

                        const result = computeStatProgression(
                            history,
                            endDate,
                            stat,
                            gamemode,
                        );

                        if (result.error) {
                            expect.unreachable(
                                `Expected success but got error: ${result.reason}`,
                            );
                        }

                        expect(result).toStrictEqual({
                            stat,
                            endValue: 110_000,
                            progressPerDay: 500,
                            nextMilestoneValue: 200_000,
                            daysUntilMilestone: 180,
                            trendingUpward: true,
                            trackingDataTimeInterval: {
                                start: startDate,
                                end: endDate,
                            },
                        });
                    });

                    test("edge case - late tracking end", () => {
                        // The tracking interval usually contains the whole current day
                        // This means we will in general always get a trackingEndDate after endDate
                        // In cases where the Hypixel API is down, this effect can be exacerbated as
                        // the endDate (the date of the last recorded stats instance in the tracking interval)
                        // can be many days old, and not just some hours earlier than trackingEndDate.
                        // This can lead to e.g. predicted milestone dates being earlier than trackingEndDate
                        const startDate = new Date("2025-01-01T00:00:00Z");
                        const endDate = new Date("2025-01-06T00:00:00Z");
                        const trackingEndDate = new Date("2025-01-11T00:00:00Z");
                        const startBuilder = new PlayerDataBuilder(
                            TEST_UUID,
                            startDate,
                        );
                        const endBuilder = new PlayerDataBuilder(TEST_UUID, endDate);
                        startBuilder.withGamemodeStats(
                            gamemode,
                            new StatsBuilder().withStat(stat, 100).build(),
                        );
                        endBuilder.withGamemodeStats(
                            gamemode,
                            new StatsBuilder().withStat(stat, 200).build(),
                        );

                        const history: History = [
                            startBuilder.build(),
                            endBuilder.build(),
                        ];

                        const result = computeStatProgression(
                            history,
                            trackingEndDate,
                            stat,
                            gamemode,
                        );

                        if (result.error) {
                            expect.unreachable(
                                `Expected success but got error: ${result.reason}`,
                            );
                        }

                        expect(result).toStrictEqual({
                            stat,
                            endValue: 200,
                            progressPerDay: 10,
                            nextMilestoneValue: 300,
                            // NOTE: This is from the endDate, so this would be just 5 days after trackingEndDate
                            daysUntilMilestone: 10,
                            trendingUpward: true,
                            trackingDataTimeInterval: {
                                start: startDate,
                                end: trackingEndDate,
                            },
                        });
                    });
                });
            }
        });
    }
});

describe("computeStatProgression - quotient stats", () => {
    const quotientStats = ["fkdr", "kdr"] as const;
    const gamemodes = ALL_GAMEMODE_KEYS;

    type QuotientStatKey = (typeof quotientStats)[number];

    const getDividendStat = (stat: QuotientStatKey) => {
        switch (stat) {
            case "fkdr": {
                return "finalKills";
            }
            case "kdr": {
                return "kills";
            }
        }
    };

    const getDivisorStat = (stat: QuotientStatKey) => {
        switch (stat) {
            case "fkdr": {
                return "finalDeaths";
            }
            case "kdr": {
                return "deaths";
            }
        }
    };

    for (const gamemode of gamemodes) {
        describe(`gamemode: ${gamemode}`, () => {
            for (const stat of quotientStats) {
                const dividendStat = getDividendStat(stat);
                const divisorStat = getDivisorStat(stat);

                describe(`stat: ${stat}`, () => {
                    test("basic - improving quotient", () => {
                        const startDate = new Date("2024-01-01T00:00:00Z");
                        const endDate = new Date("2024-01-11T00:00:00Z"); // 10 days
                        const startBuilder = new StatsBuilder();
                        const endBuilder = new StatsBuilder();

                        // Start: 100/50 = 2.0
                        // End: 200/75 = 2.66... (improving)
                        startBuilder
                            .withStat(dividendStat, 100)
                            .withStat(divisorStat, 50);
                        endBuilder
                            .withStat(dividendStat, 200)
                            .withStat(divisorStat, 75);

                        const history: History = [
                            new PlayerDataBuilder(TEST_UUID, startDate)
                                .withGamemodeStats(gamemode, startBuilder.build())
                                .build(),
                            new PlayerDataBuilder(TEST_UUID, endDate)
                                .withGamemodeStats(gamemode, endBuilder.build())
                                .build(),
                        ];

                        const result = computeStatProgression(
                            history,
                            endDate,
                            stat,
                            gamemode,
                        );

                        if (result.error) {
                            expect.unreachable(
                                `Expected success but got error: ${result.reason}`,
                            );
                        }

                        expect(result).toStrictEqual({
                            stat,
                            endValue: 200 / 75,
                            sessionQuotient: 100 / 25,
                            // (Goal - current) / days to reach
                            // NOTE: This will be higher at first and decrease over time,
                            // especially if the session quotient is close to the next milestone,
                            // but this is the current simple way of calculating something sensible here
                            progressPerDay: (3 - 200 / 75) / 10,
                            dividendPerDay: 100 / 10,
                            divisorPerDay: 25 / 10,
                            nextMilestoneValue: 3,
                            daysUntilMilestone: 10, // 100 more dividend and 25 more divisor
                            trendingUpward: true,
                            trackingDataTimeInterval: {
                                start: startDate,
                                end: endDate,
                            },
                        });
                    });

                    test("basic - declining quotient", () => {
                        const startDate = new Date("2024-01-01T00:00:00Z");
                        const endDate = new Date("2024-01-11T00:00:00Z");
                        const startBuilder = new StatsBuilder();
                        const endBuilder = new StatsBuilder();

                        // Start: 100/50 = 2.0
                        // End: 150/125 = 1.2 (declining)
                        startBuilder
                            .withStat(dividendStat, 100)
                            .withStat(divisorStat, 50);
                        endBuilder
                            .withStat(dividendStat, 150)
                            .withStat(divisorStat, 125);

                        const history: History = [
                            new PlayerDataBuilder(TEST_UUID, startDate)
                                .withGamemodeStats(gamemode, startBuilder.build())
                                .build(),
                            new PlayerDataBuilder(TEST_UUID, endDate)
                                .withGamemodeStats(gamemode, endBuilder.build())
                                .build(),
                        ];

                        const result = computeStatProgression(
                            history,
                            endDate,
                            stat,
                            gamemode,
                        );

                        if (result.error) {
                            expect.unreachable(
                                `Expected success but got error: ${result.reason}`,
                            );
                        }

                        expect(result).toStrictEqual({
                            stat,
                            endValue: 150 / 125,
                            sessionQuotient: 50 / 75,
                            // (Goal - current) / days to reach
                            progressPerDay: (1 - 1.2) / 10,
                            dividendPerDay: 50 / 10,
                            divisorPerDay: 75 / 10,
                            nextMilestoneValue: 1,
                            daysUntilMilestone: 10, // 50 more dividend and 75 more divisor
                            trendingUpward: false,
                            trackingDataTimeInterval: {
                                start: startDate,
                                end: endDate,
                            },
                        });
                    });

                    test("edge case - zero divisor overall", () => {
                        // With a zero divisor overall, the quotient is defined as just the dividend
                        // This means that this is equivalent to a linear stat progression on the dividend stat
                        const startDate = new Date("2024-01-01T00:00:00Z");
                        const endDate = new Date("2024-01-11T00:00:00Z");
                        const startBuilder = new StatsBuilder();
                        const endBuilder = new StatsBuilder();

                        // Zero divisor overall (also within tracking interval)
                        startBuilder
                            .withStat(dividendStat, 100)
                            .withStat(divisorStat, 0);
                        endBuilder.withStat(dividendStat, 200).withStat(divisorStat, 0);

                        const history: History = [
                            new PlayerDataBuilder(TEST_UUID, startDate)
                                .withGamemodeStats(gamemode, startBuilder.build())
                                .build(),
                            new PlayerDataBuilder(TEST_UUID, endDate)
                                .withGamemodeStats(gamemode, endBuilder.build())
                                .build(),
                        ];

                        const result = computeStatProgression(
                            history,
                            endDate,
                            stat,
                            gamemode,
                        );

                        if (result.error) {
                            expect.unreachable(
                                `Expected success but got error: ${result.reason}`,
                            );
                        }

                        expect(result).toStrictEqual({
                            stat,
                            endValue: 200,
                            sessionQuotient: 100, // Quotient is just dividend when divisor is zero
                            progressPerDay: 10, // Linear progress of dividend
                            dividendPerDay: 10,
                            divisorPerDay: 0,
                            nextMilestoneValue: 300,
                            daysUntilMilestone: 10,
                            trendingUpward: true,
                            trackingDataTimeInterval: {
                                start: startDate,
                                end: endDate,
                            },
                        });
                    });

                    describe("edge case - zero session divisor", () => {
                        // NOTE: Milestones are kind of awkward for high quotients
                        const cases = [
                            {
                                divisor: 1,
                                goal: 201, // 200 -> 201
                                daysToReach: 0.1, // 1 dividend => 1/10 days
                            },
                            {
                                divisor: 5,
                                goal: 41, // 40 -> 41
                                daysToReach: 0.5, // 5 dividend => 5/10 days
                            },
                            {
                                divisor: 10,
                                goal: 21, // 20 -> 21
                                daysToReach: 1, // 10 dividend => 10/10 days
                            },
                            {
                                divisor: 100,
                                goal: 3, // 2 -> 3
                                daysToReach: 10, // 100 dividend => 100/10 days
                            },
                        ];
                        for (const { divisor, goal, daysToReach } of cases) {
                            test(`divisor constant at ${divisor.toString()}`, () => {
                                // The player did not gain any divisor during the tracking interval
                                // The quotient will grow linearly with the dividend, divided by the constant divisor
                                const startDate = new Date("2024-01-01T00:00:00Z");
                                const endDate = new Date("2024-01-11T00:00:00Z");
                                const startBuilder = new StatsBuilder();
                                const endBuilder = new StatsBuilder();

                                startBuilder
                                    .withStat(dividendStat, 100)
                                    .withStat(divisorStat, divisor);
                                endBuilder
                                    .withStat(dividendStat, 200)
                                    .withStat(divisorStat, divisor);

                                const history: History = [
                                    new PlayerDataBuilder(TEST_UUID, startDate)
                                        .withGamemodeStats(
                                            gamemode,
                                            startBuilder.build(),
                                        )
                                        .build(),
                                    new PlayerDataBuilder(TEST_UUID, endDate)
                                        .withGamemodeStats(gamemode, endBuilder.build())
                                        .build(),
                                ];

                                const result = computeStatProgression(
                                    history,
                                    endDate,
                                    stat,
                                    gamemode,
                                );

                                if (result.error) {
                                    expect.unreachable(
                                        `Expected success but got error: ${result.reason}`,
                                    );
                                }

                                expect(result).toStrictEqual({
                                    stat,
                                    endValue: 200 / divisor,
                                    sessionQuotient: 100, // Quotient is just dividend when divisor is 0
                                    // (goal - current) / days to reach
                                    progressPerDay:
                                        (goal - 200 / divisor) / daysToReach,
                                    dividendPerDay: 10,
                                    divisorPerDay: 0,
                                    nextMilestoneValue: goal,
                                    daysUntilMilestone: daysToReach,
                                    trendingUpward: true,
                                    trackingDataTimeInterval: {
                                        start: startDate,
                                        end: endDate,
                                    },
                                });
                            });
                        }
                    });

                    test("edge case - goal quotient equal to session quotient (up)", () => {
                        const startDate = new Date("2024-01-01T00:00:00Z");
                        const endDate = new Date("2024-01-11T00:00:00Z");
                        const startBuilder = new StatsBuilder();
                        const endBuilder = new StatsBuilder();

                        startBuilder.withStat(dividendStat, 0).withStat(divisorStat, 5);
                        endBuilder.withStat(dividendStat, 10).withStat(divisorStat, 10);

                        const history: History = [
                            new PlayerDataBuilder(TEST_UUID, startDate)
                                .withGamemodeStats(gamemode, startBuilder.build())
                                .build(),
                            new PlayerDataBuilder(TEST_UUID, endDate)
                                .withGamemodeStats(gamemode, endBuilder.build())
                                .build(),
                        ];

                        const result = computeStatProgression(
                            history,
                            endDate,
                            stat,
                            gamemode,
                        );

                        if (result.error) {
                            expect.unreachable(
                                `Expected success but got error: ${result.reason}`,
                            );
                        }

                        expect(result).toStrictEqual({
                            stat,
                            endValue: 1,
                            sessionQuotient: 2,
                            progressPerDay: 0,
                            dividendPerDay: 1,
                            divisorPerDay: 0.5,
                            nextMilestoneValue: 2,
                            daysUntilMilestone: Infinity,
                            trendingUpward: true,
                            trackingDataTimeInterval: {
                                start: startDate,
                                end: endDate,
                            },
                        });
                    });

                    test("edge case - goal quotient equal to session quotient (down)", () => {
                        const startDate = new Date("2024-01-01T00:00:00Z");
                        const endDate = new Date("2024-01-11T00:00:00Z");
                        const startBuilder = new StatsBuilder();
                        const endBuilder = new StatsBuilder();

                        startBuilder.withStat(dividendStat, 5).withStat(divisorStat, 0);
                        endBuilder.withStat(dividendStat, 10).withStat(divisorStat, 5);

                        const history: History = [
                            new PlayerDataBuilder(TEST_UUID, startDate)
                                .withGamemodeStats(gamemode, startBuilder.build())
                                .build(),
                            new PlayerDataBuilder(TEST_UUID, endDate)
                                .withGamemodeStats(gamemode, endBuilder.build())
                                .build(),
                        ];

                        const result = computeStatProgression(
                            history,
                            endDate,
                            stat,
                            gamemode,
                        );

                        if (result.error) {
                            expect.unreachable(
                                `Expected success but got error: ${result.reason}`,
                            );
                        }

                        expect(result).toStrictEqual({
                            stat,
                            endValue: 2,
                            sessionQuotient: 1,
                            progressPerDay: 0,
                            dividendPerDay: 0.5,
                            divisorPerDay: 0.5,
                            nextMilestoneValue: 1,
                            daysUntilMilestone: Infinity,
                            trendingUpward: false,
                            trackingDataTimeInterval: {
                                start: startDate,
                                end: endDate,
                            },
                        });
                    });

                    test("edge case - goal quotient higher than session quotient (up)", () => {
                        const startDate = new Date("2024-01-01T00:00:00Z");
                        const endDate = new Date("2024-01-11T00:00:00Z");
                        const startBuilder = new StatsBuilder();
                        const endBuilder = new StatsBuilder();

                        startBuilder.withStat(dividendStat, 1).withStat(divisorStat, 5);
                        endBuilder.withStat(dividendStat, 10).withStat(divisorStat, 10);

                        const history: History = [
                            new PlayerDataBuilder(TEST_UUID, startDate)
                                .withGamemodeStats(gamemode, startBuilder.build())
                                .build(),
                            new PlayerDataBuilder(TEST_UUID, endDate)
                                .withGamemodeStats(gamemode, endBuilder.build())
                                .build(),
                        ];

                        const result = computeStatProgression(
                            history,
                            endDate,
                            stat,
                            gamemode,
                        );

                        if (result.error) {
                            expect.unreachable(
                                `Expected success but got error: ${result.reason}`,
                            );
                        }

                        expect(result).toStrictEqual({
                            stat,
                            endValue: 1,
                            sessionQuotient: 9 / 5,
                            progressPerDay: 0,
                            dividendPerDay: 0.9,
                            divisorPerDay: 0.5,
                            nextMilestoneValue: 2,
                            daysUntilMilestone: Infinity,
                            trendingUpward: true,
                            trackingDataTimeInterval: {
                                start: startDate,
                                end: endDate,
                            },
                        });
                    });

                    test("edge case - goal quotient lower than session quotient (down)", () => {
                        const startDate = new Date("2024-01-01T00:00:00Z");
                        const endDate = new Date("2024-01-11T00:00:00Z");
                        const startBuilder = new StatsBuilder();
                        const endBuilder = new StatsBuilder();

                        startBuilder.withStat(dividendStat, 4).withStat(divisorStat, 0);
                        endBuilder.withStat(dividendStat, 10).withStat(divisorStat, 5);

                        const history: History = [
                            new PlayerDataBuilder(TEST_UUID, startDate)
                                .withGamemodeStats(gamemode, startBuilder.build())
                                .build(),
                            new PlayerDataBuilder(TEST_UUID, endDate)
                                .withGamemodeStats(gamemode, endBuilder.build())
                                .build(),
                        ];

                        const result = computeStatProgression(
                            history,
                            endDate,
                            stat,
                            gamemode,
                        );

                        if (result.error) {
                            expect.unreachable(
                                `Expected success but got error: ${result.reason}`,
                            );
                        }

                        expect(result).toStrictEqual({
                            stat,
                            endValue: 2,
                            sessionQuotient: 1.2,
                            progressPerDay: 0,
                            dividendPerDay: 0.6,
                            divisorPerDay: 0.5,
                            nextMilestoneValue: 1,
                            daysUntilMilestone: Infinity,
                            trendingUpward: false,
                            trackingDataTimeInterval: {
                                start: startDate,
                                end: endDate,
                            },
                        });
                    });
                });
            }
        });
    }
});

describe("computeStatProgression - stars/experience stat", () => {
    const gamemodes = ALL_GAMEMODE_KEYS;

    // Note: stars+experience are overall stats, but we test it across
    // all gamemodes to verify the API correctly handles
    // overall stats when queried with gamemode-specific keys
    for (const gamemode of gamemodes) {
        describe(`gamemode: ${gamemode}`, () => {
            describe("basic - steady exp gain", () => {
                const startDate = new Date("2024-01-01T00:00:00Z");
                const endDate = new Date("2024-01-11T00:00:00Z"); // 10 days
                // Start at 500 exp (1 star), gain 5000 exp in 10 days
                const history: History = [
                    new PlayerDataBuilder(TEST_UUID, startDate)
                        .withExperience(500)
                        .build(),
                    new PlayerDataBuilder(TEST_UUID, endDate)
                        .withExperience(7000)
                        .build(),
                ];

                test("stars", () => {
                    const result = computeStatProgression(
                        history,
                        endDate,
                        "stars",
                        gamemode,
                    );

                    if (result.error) {
                        expect.unreachable(
                            `Expected success but got error: ${result.reason}`,
                        );
                    }

                    const {
                        daysUntilMilestone,
                        progressPerDay,
                        ...resultWithoutTrickyFloats
                    } = result;

                    expect(resultWithoutTrickyFloats).toStrictEqual({
                        stat: "stars",
                        endValue: 4,
                        nextMilestoneValue: 100,
                        trendingUpward: true,
                        trackingDataTimeInterval: {
                            start: startDate,
                            end: endDate,
                        },
                    });

                    // (exp gained / avg exp per star) / days
                    const expectedStarsPerDay = 6500 / 4870 / 10;
                    expect(progressPerDay).toBeCloseTo(expectedStarsPerDay);

                    // Exp remaining until 100 stars / (exp per day)
                    const expectedDaysUntilMilestone = (487_000 - 7000) / (6500 / 10);
                    expect(daysUntilMilestone).toBeCloseTo(expectedDaysUntilMilestone);
                });

                test("experience", () => {
                    const result = computeStatProgression(
                        history,
                        endDate,
                        "experience",
                        gamemode,
                    );

                    if (result.error) {
                        expect.unreachable(
                            `Expected success but got error: ${result.reason}`,
                        );
                    }

                    expect(result).toStrictEqual({
                        stat: "experience",
                        endValue: 7000,
                        progressPerDay: 650,
                        nextMilestoneValue: 8000,
                        daysUntilMilestone: 1000 / 650,
                        trendingUpward: true,
                        trackingDataTimeInterval: {
                            start: startDate,
                            end: endDate,
                        },
                    });
                });
            });
        });
    }
});

describe("computeStatProgression - index stat", () => {
    describe("success cases", () => {
        // Note: Index = fkdr^2 * stars
        //       We use average exp per star for progression: PRESTIGE_EXP / 100 = 487000 / 100 = 4870
        //       We use actual star calculation for index calculation
        //       const EASY_LEVEL_COSTS = { 1: 500, 2: 1000, 3: 2000, 4: 3500 }; Rest: 5000

        // Given:
        //  s_0 = initial stars
        //  s   = stars gained per day
        //  k_0 = initial final kills
        //  k   = final kills gained per day
        //  d_0 = initial final deaths
        //  d   = final deaths gained per day
        //  M   = target index milestone
        //  t   = days until milestone
        //
        // We have:
        // index(t) = (s_0 + s*t) * (k_0+k*t)^2/(d_0+d*t)^2 = M
        // -> (s_0 + s*t) * (k_0^2 + 2k_0*k*t + k^2*t^2) / (d_0^2 + 2d_0*d*t + d^2*t^2) = M
        // -> (s_0 + s*t) * (k_0^2 + 2k_0*k*t + k^2*t^2) = M * (d_0^2 + 2d_0*d*t + d^2*t^2)
        // -> s_0*k_0^2 + 2s_0*k_0*k*t + s_0*k^2*t^2 + s*k_0^2*t + 2s*k_0*k*t^2 + s*k^2*t^3 = M*d_0^2 + 2M*d_0*d*t + M*d^2*t^2
        // -> s*k^2*t^3 + s_0*k^2*t^2 + 2s*k_0*k*t^2 - M*d^2*t^2 + 2s_0*k_0*k*t + s*k_0^2*t - 2M*d_0*d*t - M*d_0^2 + s_0*k_0^2 = 0
        // -> (s*k^2)*t^3 + (s_0*k^2 + 2s*k_0*k - M*d^2)*t^2 + (2s_0*k_0*k + s*k_0^2 - 2M*d_0*d)*t + (s_0*k_0^2 - M*d_0^2) = 0
        // -> a = s*k^2
        //    b = s_0*k^2 + 2s*k_0*k - M*d^2
        //    c = 2s_0*k_0*k + s*k_0^2 - 2M*d_0*d
        //    d = s_0*k_0^2 - M*d_0^2
        //
        // Interesting edge cases:
        //  a = 0
        //  a = 0 ^ b = 0
        //  a = 0 ^ b = 0 ^ c = 0
        //
        // Discriminant: 18abcd - 4b^3d + b^2c^2 - 4ac^3 -27a^2d^2
        //  Positive
        //  Zero
        //  Negative

        const computeCoefficients = (c: Case) => {
            const s0 = bedwarsLevelFromExp(c.trackingStats.end.experience);
            const s =
                (c.trackingStats.end.experience - c.trackingStats.start.experience) /
                4870 /
                c.trackingStats.durationDays;
            const k0 = c.trackingStats.end.finalKills;
            const k =
                (c.trackingStats.end.finalKills - c.trackingStats.start.finalKills) /
                c.trackingStats.durationDays;
            const d0 = c.trackingStats.end.finalDeaths;
            const d =
                (c.trackingStats.end.finalDeaths - c.trackingStats.start.finalDeaths) /
                c.trackingStats.durationDays;
            const M = c.expected.milestone;
            return {
                a: s * k * k,
                b: s0 * k * k + 2 * s * k0 * k - M * d * d,
                c: 2 * s0 * k0 * k + s * k0 * k0 - 2 * M * d0 * d,
                d: s0 * k0 * k0 - M * d0 * d0,
            } as const;
        };

        const computeDiscriminant = ({
            a,
            b,
            c,
            d,
        }: ReturnType<typeof computeCoefficients>) => {
            return (
                18 * a * b * c * d -
                4 * b * b * b * d +
                b * b * c * c -
                4 * a * c * c * c -
                27 * a * a * d * d
            );
        };

        type Sign = "positive" | "zero" | "negative";

        interface Case {
            readonly name: string;
            readonly trackingStats: {
                readonly durationDays: number;
                readonly start: {
                    readonly experience: number;
                    readonly finalKills: number;
                    readonly finalDeaths: number;
                };
                readonly end: {
                    readonly experience: number;
                    readonly finalKills: number;
                    readonly finalDeaths: number;
                };
            };
            readonly expected: {
                readonly index: number;
                readonly milestone: number;
                readonly daysUntilMilestone: number;
                readonly progressPerDay: number;
                readonly cubic?: {
                    readonly discriminant: Sign;
                    readonly a: Sign;
                    readonly b: Sign;
                    readonly c: Sign;
                    readonly d: Sign;
                };
            };
        }

        const cases: Case[] = [
            {
                name: "no progress",
                trackingStats: {
                    durationDays: 10,
                    start: {
                        // No progress
                        experience: 7000,
                        finalKills: 10,
                        finalDeaths: 5,
                    },
                    end: {
                        experience: 7000, // 4 stars
                        finalKills: 10, // 2 fkdr
                        finalDeaths: 5,
                    },
                },
                expected: {
                    index: 16, // 4 stars * (2 fkdr)^2
                    milestone: 20,
                    daysUntilMilestone: Infinity,
                    progressPerDay: 0,
                    cubic: {
                        discriminant: "zero",
                        a: "zero",
                        b: "zero",
                        c: "zero",
                        d: "negative",
                    },
                },
            },
            {
                name: "no finals",
                trackingStats: {
                    durationDays: 10,
                    start: {
                        experience: 500,
                        finalKills: 0,
                        finalDeaths: 5,
                    },
                    end: {
                        experience: 7000, // 4 stars
                        finalKills: 0, // 0 fkdr
                        finalDeaths: 10,
                    },
                },
                expected: {
                    index: 0, // 4 stars * (0 fkdr)^2
                    milestone: 1,
                    daysUntilMilestone: Infinity, // constant fkdr at 0
                    progressPerDay: 0,
                    cubic: {
                        discriminant: "zero",
                        a: "zero",
                        b: "negative",
                        c: "negative",
                        d: "negative",
                    },
                },
            },
            {
                name: "no stars",
                trackingStats: {
                    durationDays: 10,
                    start: {
                        experience: 0, // NOTE: 0 stars is not possible to attain, as all players start with 500 exp
                        finalKills: 0,
                        finalDeaths: 1,
                    },
                    end: {
                        experience: 0, // 0 stars
                        finalKills: 100,
                        finalDeaths: 1,
                    },
                },
                expected: {
                    index: 0, // 0 stars * (100 fkdr)^2
                    milestone: 1,
                    daysUntilMilestone: Infinity, // constant stars at 0
                    progressPerDay: 0,
                    cubic: {
                        discriminant: "zero",
                        a: "zero",
                        b: "zero",
                        c: "zero",
                        d: "negative",
                    },
                },
            },
            {
                name: "increasing star, stable fkdr",
                trackingStats: {
                    durationDays: 10,
                    start: {
                        experience: 2130, // 4870 (1 avg star) difference
                        finalKills: 10, // 2 fkdr -> 2 session fkdr
                        finalDeaths: 5,
                    },
                    end: {
                        experience: 7000, // 4 stars
                        finalKills: 20, // 2 fkdr
                        finalDeaths: 10,
                    },
                },
                expected: {
                    index: 16, // 4 stars * (2 fkdr)^2
                    milestone: 20,
                    daysUntilMilestone: 10, // stable fkdr -> need to get to 5 stars (gain 1 star) -> 10 days (same as tracking interval)
                    progressPerDay: 0.4,
                    cubic: {
                        discriminant: "zero",
                        a: "positive",
                        b: "positive",
                        c: "zero",
                        d: "negative",
                    },
                },
            },
            {
                name: "increasing fkdr, zero final deaths, stable stars",
                // NOTE: In this case the equation changes as we calculate fkdr as just final kills
                //       -> We skip the assertions about the shape of the cubic equation
                trackingStats: {
                    durationDays: 10,
                    start: {
                        experience: 500, // 0 star progress - not really possible, but interesting to test
                        finalKills: 10, // 1 final per day
                        finalDeaths: 0,
                    },
                    end: {
                        experience: 500,
                        finalKills: 20, // 20 fkdr, trending up by 1 fkdr/day
                        finalDeaths: 0,
                    },
                },
                expected: {
                    index: 400, // 1 star * (20 fkdr)^2
                    milestone: 500,
                    /* 500 index
                     * -> sqrt(500) fkdr
                     * -> 20 + t = sqrt(500)
                     * -> t = sqrt(500) - 20
                     */
                    daysUntilMilestone: Math.sqrt(500) - 20,
                    /* (500-400) / daysUntilMilestone
                     *      = (100) / (sqrt(500) - 20)
                     *      = (100 * (sqrt(500) + 20)) / (500 - 400)
                     *      = sqrt(500) + 20
                     */
                    progressPerDay: Math.sqrt(500) + 20,
                },
            },
            {
                name: "increasing fkdr, stable final deaths, stable stars",
                trackingStats: {
                    durationDays: 10,
                    start: {
                        experience: 500, // 0 star progress - not really possible, but interesting to test
                        finalKills: 10, // 1 final per day
                        finalDeaths: 2, // Non-zero stable final deaths
                    },
                    end: {
                        experience: 500,
                        finalKills: 20, // 10 fkdr, trending up by 0.5 fkdr/day
                        finalDeaths: 2,
                    },
                },
                expected: {
                    index: 100, // 1 star * (10 fkdr)^2
                    milestone: 200,
                    /* 200 index
                     * -> sqrt(200) fkdr
                     * -> (20 + t)/2 = sqrt(200)
                     * -> t = 2 * sqrt(200) - 20 = 20*sqrt(2) - 20
                     */
                    daysUntilMilestone: 20 * Math.SQRT2 - 20,
                    /* (200-100) / daysUntilMilestone
                     *      = 100 / (20*sqrt(2) - 20)
                     *      = 100 * (20*sqrt(2) + 20) / (800 - 400)
                     *      = 5*sqrt(2)+5
                     */
                    progressPerDay: 5 * Math.SQRT2 + 5,
                    cubic: {
                        discriminant: "positive",
                        a: "zero",
                        b: "positive",
                        c: "positive",
                        d: "negative",
                    },
                },
            },
            {
                name: "increasing fkdr, stable stars",
                trackingStats: {
                    durationDays: 10,
                    start: {
                        experience: 500, // 0 star progress - not really possible, but interesting to test
                        finalKills: 0, // 2 finals per day (20 session fkdr)
                        finalDeaths: 1, // 0.1 final death per day
                    },
                    end: {
                        experience: 500,
                        finalKills: 20, // 10 fkdr
                        finalDeaths: 2,
                    },
                },
                expected: {
                    index: 100, // 1 star * (10 fkdr)^2
                    milestone: 200,
                    /* 200 index
                     * -> sqrt(200) fkdr
                     * -> (20 + 2t) / (2+0.1t)
                     *      = sqrt(200) -> 20 + 2t
                     *      = 2*sqrt(200)+0.1*sqrt(200)*t
                     * -> t = (2 * sqrt(200) - 20) / (2 - 0.1*sqrt(200))
                     *      = (20*sqrt(2) - 20) / (2 - sqrt(2))
                     *      = (20*sqrt(2)-20)*(2 + sqrt(2)) / (4 - 2)
                     *      = (40*sqrt(2) + 40 - 40 - 20*sqrt(2)) / 2
                     *      = 10*sqrt(2)
                     */
                    daysUntilMilestone: 10 * Math.SQRT2,
                    /* (200-100) / daysUntilMilestone
                     *      = 100 / (10*sqrt(2))
                     *      = 5*sqrt(2)
                     */
                    progressPerDay: 5 * Math.SQRT2,
                    cubic: {
                        discriminant: "positive",
                        a: "zero",
                        b: "positive",
                        c: "zero",
                        d: "negative",
                    },
                },
            },
            {
                name: "increasing plateauing fkdr, stable stars",
                trackingStats: {
                    durationDays: 10,
                    start: {
                        experience: 500, // 0 star progress - not really possible, but interesting to test
                        finalKills: 16, // 2 finals per day (20 session fkdr)
                        finalDeaths: 1, // 0.1 final death per day
                    },
                    end: {
                        experience: 500,
                        finalKills: 36, // 18 fkdr
                        finalDeaths: 2,
                    },
                },
                expected: {
                    index: 324, // 1 star * (18 fkdr)^2
                    milestone: 400,
                    /* 400 index
                     * -> sqrt(400) = 20 fkdr
                     * This is our session fkdr, so we will asymptotically approach it but never reach it
                     * -> Milestone is unreachable
                     */
                    daysUntilMilestone: Infinity,
                    // (400-324) / Infinity = 0
                    progressPerDay: 0,
                    cubic: {
                        discriminant: "zero",
                        a: "zero",
                        b: "zero",
                        c: "negative",
                        d: "negative",
                    },
                },
            },
            {
                name: "decreasing fkdr, stable stars",
                trackingStats: {
                    durationDays: 10,
                    start: {
                        experience: 500, // 0 star progress - not really possible, but interesting to test
                        finalKills: 15, // 0.5 final per day (5 session fkdr)
                        finalDeaths: 1, // 0.1 final death per day
                    },
                    end: {
                        experience: 500,
                        finalKills: 20, // 10 fkdr
                        finalDeaths: 2,
                    },
                },
                expected: {
                    index: 100, // 1 star * (10 fkdr)^2
                    milestone: 90,
                    /* 90 index
                     * -> sqrt(90) fkdr
                     * -> (20+0.5*t)/(2+0.1*t) = sqrt(90)
                     * -> (20+0.5*t) = 2*sqrt(90) + sqrt(90)*0.1*t
                     * -> t*(0.5 - 0.1*sqrt(90)) = 2*sqrt(90) - 20
                     * -> t = (2*sqrt(90)-20) / (0.5 - 0.1*sqrt(90))
                     *      = (60*sqrt(10)-200) / (5 - 3*sqrt(10))
                     *      = (60*sqrt(10)-200) * (5 + 3*sqrt(10)) / (25 - 90)
                     *      = 300*sqrt(10) + 1800 - 1000 - 600*sqrt(10)) / -65
                     *      = (300*sqrt(10) - 800) / 65
                     *      = (60*sqrt(10) - 160) / 13
                     */
                    daysUntilMilestone: (60 * Math.sqrt(10) - 160) / 13,
                    /* (90-100) / daysUntilMilestone
                     *      = -10 / ((60*sqrt(10) - 160) / 13)
                     *      = -130 * (60*sqrt(10) + 160) / (36000 - 25600)
                     *      = -(20800 + 7800*sqrt(10)) / 10400
                     *      = -(8 + 3*sqrt(10)) / 4
                     */
                    progressPerDay: -(8 + 3 * Math.sqrt(10)) / 4,
                    cubic: {
                        discriminant: "positive",
                        a: "zero",
                        b: "negative",
                        c: "negative",
                        d: "positive",
                    },
                },
            },
            {
                name: "decreasing plateauing fkdr, stable stars",
                trackingStats: {
                    durationDays: 10,
                    start: {
                        experience: 500, // 0 star progress - not really possible, but interesting to test
                        finalKills: 16, // 0.5 final per day (5 session fkdr)
                        finalDeaths: 3, // 0.1 final death per day
                    },
                    end: {
                        experience: 500,
                        finalKills: 21, // 5.25 fkdr
                        finalDeaths: 4,
                    },
                },
                expected: {
                    index: 27.5625, // 1 star * (5.25 fkdr)^2
                    milestone: 20,
                    /* 20 index
                     * -> sqrt(20) fkdr
                     * This is below our session fkdr. We will asymptotically approach 25,
                     * but never reach it or anything below.
                     * -> Milestone is unreachable
                     */
                    daysUntilMilestone: Infinity,
                    // (20-27.5625) / Infinity = 0
                    progressPerDay: 0,
                    cubic: {
                        discriminant: "positive",
                        a: "zero",
                        b: "positive",
                        c: "positive",
                        d: "positive",
                    },
                },
            },
            {
                name: "index decreasing past next milestone before increasing",
                trackingStats: {
                    durationDays: 10,
                    start: {
                        experience: 2130, // 1 avg stars gained (0.1 stars per day)
                        finalKills: 60, // 2 finals per day
                        finalDeaths: 3, // 0.5 final death per day
                    },
                    end: {
                        experience: 7000, // 4 stars
                        finalKills: 80, // 10 fkdr
                        finalDeaths: 8,
                    },
                },
                expected: {
                    // index(t) = (4 + 0.1*t) * (80+2*t)^2/(8+0.5*t)^2
                    index: 400, // 4 star * (10 fkdr)^2
                    milestone: 300,
                    // Shamelessly solved by WolframAlpha
                    daysUntilMilestone: 9.211_65,
                    // (300 - 400) / daysUntilMilestone
                    progressPerDay: -100 / 9.211_65,
                    cubic: {
                        discriminant: "positive",
                        a: "positive",
                        b: "negative",
                        c: "negative",
                        d: "positive",
                    },
                },
            },
            {
                name: "index decreasing not reaching next milestone before increasing",
                trackingStats: {
                    durationDays: 2,
                    start: {
                        experience: 2526, // 0.2 avg stars gained (0.1 stars per day)
                        finalKills: 76, // 2 finals per day
                        finalDeaths: 7, // 0.5 final death per day
                    },
                    end: {
                        experience: 3500, // 3 stars
                        finalKills: 80, // 10 fkdr
                        finalDeaths: 8,
                    },
                },
                expected: {
                    // index(t) = (3 + 0.1*t) * (80+2*t)^2/(8+0.5*t)^2
                    index: 300, // 3 star * (10 fkdr)^2
                    milestone: 200,
                    // Reaches minimum just above 200 at around t=24 days
                    daysUntilMilestone: Infinity,
                    // (200 - 300) / daysUntilMilestone
                    progressPerDay: 0,
                    cubic: {
                        discriminant: "negative",
                        a: "positive",
                        b: "negative",
                        c: "zero",
                        d: "positive",
                    },
                },
            },
            {
                name: "index increasing past next milestone",
                trackingStats: {
                    durationDays: 10,
                    start: {
                        experience: 690 * 4870, // 10 avg stars gained (1 star per day)
                        finalKills: 17_800, // 20 finals per day
                        finalDeaths: 1790, // 1 final death per day
                    },
                    end: {
                        experience: 700 * 4870, // 700 stars
                        finalKills: 18_000, // 10 fkdr
                        finalDeaths: 1800,
                    },
                },
                expected: {
                    // index(t) = (700 + 1*t) * (18000+20*t)^2/(1800+1*t)^2
                    index: 70_000, // 700 star * (10 fkdr)^2
                    milestone: 80_000,
                    // Shamelessly solved by WolframAlpha
                    daysUntilMilestone: 54.768,
                    // (80_000 - 70_000) / daysUntilMilestone
                    progressPerDay: 10_000 / 54.768,
                    cubic: {
                        discriminant: "negative",
                        a: "positive",
                        b: "positive",
                        c: "positive",
                        d: "negative",
                    },
                },
            },
        ];

        for (const c of cases) {
            test(c.name, () => {
                if (c.expected.cubic) {
                    const checkCoefficientSign = (
                        value: number,
                        expected: Sign,
                        name: string,
                    ) => {
                        switch (expected) {
                            case "positive": {
                                expect(
                                    value,
                                    `${name} should be positive, got ${value.toString()}`,
                                ).toBeGreaterThan(0);
                                break;
                            }
                            case "zero": {
                                expect(
                                    Math.abs(value),
                                    `${name} should be zero, got ${value.toString()}`,
                                ).toBeLessThan(1e-6);
                                break;
                            }
                            case "negative": {
                                expect(
                                    value,
                                    `${name} should be negative, got ${value.toString()}`,
                                ).toBeLessThan(0);
                                break;
                            }
                            default: {
                                expected satisfies never;
                            }
                        }
                    };

                    const coefficients = computeCoefficients(c);
                    const discriminant = computeDiscriminant(coefficients);

                    checkCoefficientSign(
                        coefficients.a,
                        c.expected.cubic.a,
                        "Coefficient a",
                    );
                    checkCoefficientSign(
                        coefficients.b,
                        c.expected.cubic.b,
                        "Coefficient b",
                    );
                    checkCoefficientSign(
                        coefficients.c,
                        c.expected.cubic.c,
                        "Coefficient c",
                    );
                    checkCoefficientSign(
                        coefficients.d,
                        c.expected.cubic.d,
                        "Coefficient d",
                    );
                    checkCoefficientSign(
                        discriminant,
                        c.expected.cubic.discriminant,
                        "Discriminant",
                    );
                }

                const startDate = new Date("2024-01-01T00:00:00Z");
                const endDate = new Date(
                    startDate.getTime() +
                        c.trackingStats.durationDays * 24 * 60 * 60 * 1000,
                );

                const history: History = [
                    new PlayerDataBuilder(TEST_UUID, startDate)
                        .withExperience(c.trackingStats.start.experience)
                        .withGamemodeStats(
                            "overall",
                            new StatsBuilder()
                                .withStat(
                                    "finalKills",
                                    c.trackingStats.start.finalKills,
                                )
                                .withStat(
                                    "finalDeaths",
                                    c.trackingStats.start.finalDeaths,
                                )
                                .build(),
                        )
                        .build(),
                    new PlayerDataBuilder(TEST_UUID, endDate)
                        .withExperience(c.trackingStats.end.experience)
                        .withGamemodeStats(
                            "overall",
                            new StatsBuilder()
                                .withStat("finalKills", c.trackingStats.end.finalKills)
                                .withStat(
                                    "finalDeaths",
                                    c.trackingStats.end.finalDeaths,
                                )
                                .build(),
                        )
                        .build(),
                ];

                const result = computeStatProgression(
                    history,
                    endDate,
                    "index",
                    "overall",
                );

                if (result.error) {
                    expect.unreachable(
                        `Expected success but got error: ${result.reason}`,
                    );
                }
                if (result.stat !== "index") {
                    expect.unreachable(`Expected stat "index", got ${result.stat}`);
                }

                // Destructure result for float comparisons
                const {
                    daysUntilMilestone,
                    progressPerDay,
                    starsPerDay,
                    finalKillsPerDay,
                    finalDeathsPerDay,
                    sessionFkdr,
                    ...rest
                } = result;

                // Deep strict equal on exact values
                expect(rest).toStrictEqual({
                    stat: "index",
                    endValue: c.expected.index,
                    nextMilestoneValue: c.expected.milestone,
                    trendingUpward: c.expected.milestone >= c.expected.index,
                    trackingDataTimeInterval: {
                        start: startDate,
                        end: endDate,
                    },
                });

                const computedReachable = daysUntilMilestone < Infinity;
                const expectedReachable = c.expected.daysUntilMilestone < Infinity;
                expect(
                    computedReachable,
                    `Milestone reachability mismatch: expected ${
                        expectedReachable ? "reachable" : "unreachable"
                    }, got ${computedReachable ? "reachable" : "unreachable"}`,
                ).toBe(expectedReachable);
                if (expectedReachable) {
                    // If the goal is reachable, the daysUntilMilestone should be close to the expected value
                    expect(
                        Math.abs(daysUntilMilestone - c.expected.daysUntilMilestone),
                        `daysUntilMilestone ${daysUntilMilestone.toString()} should be close to ${c.expected.daysUntilMilestone.toString()}`,
                    ).toBeLessThan(1e-3);
                }

                expect(
                    Math.abs(progressPerDay - c.expected.progressPerDay),
                    `progressPerDay ${progressPerDay.toString()} should be close to ${c.expected.progressPerDay.toString()}`,
                ).toBeLessThan(1e-3);

                // Sub-rate breakdowns: same definitions as computeCoefficients above.
                const expectedStarsPerDay =
                    (c.trackingStats.end.experience -
                        c.trackingStats.start.experience) /
                    4870 /
                    c.trackingStats.durationDays;
                const expectedFinalKillsPerDay =
                    (c.trackingStats.end.finalKills -
                        c.trackingStats.start.finalKills) /
                    c.trackingStats.durationDays;
                const expectedFinalDeathsPerDay =
                    (c.trackingStats.end.finalDeaths -
                        c.trackingStats.start.finalDeaths) /
                    c.trackingStats.durationDays;
                const expectedSessionFkdr =
                    expectedFinalDeathsPerDay === 0
                        ? expectedFinalKillsPerDay
                        : expectedFinalKillsPerDay / expectedFinalDeathsPerDay;

                expect(starsPerDay).toBeCloseTo(expectedStarsPerDay, 9);
                expect(finalKillsPerDay).toBeCloseTo(expectedFinalKillsPerDay, 9);
                expect(finalDeathsPerDay).toBeCloseTo(expectedFinalDeathsPerDay, 9);
                expect(sessionFkdr).toBeCloseTo(expectedSessionFkdr, 9);
            });
        }
    });
});

describe(findSmallestPositiveCubicRoot, () => {
    // Fixtures generated by tmp/index_verify/gen_test_cases.py — every
    // expected value is sympy-verified. Closed forms substituted in below
    // where one exists, so the test reads as exact derivations rather than
    // opaque floats.
    const cases: {
        name: string;
        a: number;
        b: number;
        c: number;
        e: number;
        expected: number | null;
    }[] = [
        { name: "all zero", a: 0.0, b: 0.0, c: 0.0, e: 0.0, expected: null },
        { name: "constant nonzero", a: 0.0, b: 0.0, c: 0.0, e: 5.0, expected: null },
        {
            name: "linear single positive root",
            a: 0.0,
            b: 0.0,
            c: 2.0,
            e: -6.0,
            expected: 3.0,
        },
        {
            name: "linear single negative root",
            a: 0.0,
            b: 0.0,
            c: 2.0,
            e: 6.0,
            expected: null,
        },
        { name: "linear root at zero", a: 0.0, b: 0.0, c: 1.0, e: 0.0, expected: null },
        {
            name: "quadratic two positive roots",
            a: 0.0,
            b: 1.0,
            c: -7.0,
            e: 10.0,
            expected: 2.0,
        },
        {
            name: "quadratic split signs (smallest=4)",
            a: 0.0,
            b: 1.0,
            c: -1.0,
            e: -12.0,
            expected: 4.0,
        },
        {
            name: "quadratic both negative",
            a: 0.0,
            b: 1.0,
            c: 5.0,
            e: 6.0,
            expected: null,
        },
        {
            name: "quadratic complex roots",
            a: 0.0,
            b: 1.0,
            c: 0.0,
            e: 4.0,
            expected: null,
        },
        {
            name: "quadratic double positive",
            a: 0.0,
            b: 1.0,
            c: -14.0,
            e: 49.0,
            expected: 7.0,
        },
        {
            name: "quadratic double at zero",
            a: 0.0,
            b: 1.0,
            c: 0.0,
            e: 0.0,
            expected: null,
        },
        {
            name: "cubic Δ<0 one positive",
            a: 1.0,
            b: -4.0,
            c: 9.0,
            e: -10.0,
            expected: 2.0,
        },
        {
            name: "cubic Δ<0 one negative",
            a: 1.0,
            b: 4.0,
            c: 9.0,
            e: 10.0,
            expected: null,
        },
        {
            name: "cubic 3 distinct positives",
            a: 1.0,
            b: -9.0,
            c: 23.0,
            e: -15.0,
            expected: 1.0,
        },
        {
            name: "cubic 3 distinct mixed",
            a: 1.0,
            b: 8.0,
            c: 7.0,
            e: -42.0,
            expected: 1.747_522_912_898_955_6,
        },
        {
            name: "cubic 3 distinct negatives",
            a: 1.0,
            b: 9.0,
            c: 23.0,
            e: 15.0,
            expected: null,
        },
        {
            name: "cubic double + single positive",
            a: 1.0,
            b: -9.0,
            c: 24.0,
            e: -20.0,
            expected: 2.0,
        },
        {
            name: "cubic triple positive",
            a: 1.0,
            b: -12.0,
            c: 48.0,
            e: -64.0,
            expected: 4.0,
        },
        {
            name: "cubic triple at zero",
            a: 1.0,
            b: 0.0,
            c: 0.0,
            e: 0.0,
            expected: null,
        },
        {
            name: "cubic t=0 double + positive",
            a: 1.0,
            b: -8.0,
            c: 15.0,
            e: 0.0,
            expected: 3.0,
        },
        {
            name: "index: no progress",
            a: 0.0,
            b: 0.0,
            c: 0.0,
            e: -100.0,
            expected: null,
        },
        {
            name: "index: no finals",
            a: 0.0,
            b: -0.25,
            c: -10.0,
            e: -100.0,
            expected: null,
        },
        { name: "index: no stars", a: 0.0, b: 0.0, c: 0.0, e: -1.0, expected: null },
        {
            name: "index: increasing star, stable fkdr",
            a: 0.1,
            b: 3.0,
            c: 0.0,
            e: -400.0,
            expected: 10.0,
        },
        {
            name: "index: incr fkdr, fd=0",
            a: 0.0,
            b: 1.0,
            c: 40.0,
            e: -100.0,
            expected: Math.sqrt(500) - 20,
        },
        {
            name: "index: incr fkdr, stable fd",
            a: 0.0,
            b: 1.0,
            c: 40.0,
            e: -400.0,
            expected: 20 * Math.SQRT2 - 20,
        },
        {
            name: "index: incr fkdr, stable stars",
            a: 0.0,
            b: 2.0,
            c: 0.0,
            e: -400.0,
            expected: 10 * Math.SQRT2,
        },
        {
            name: "index: incr plateauing fkdr",
            a: 0.0,
            b: 0.0,
            c: -16.0,
            e: -304.0,
            expected: null,
        },
        {
            name: "index: decr fkdr, stable stars",
            a: 0.0,
            b: -0.65,
            c: -16.0,
            e: 40.0,
            expected: (60 * Math.sqrt(10) - 160) / 13,
        },
        {
            name: "index: decr plateauing fkdr",
            a: 0.0,
            b: 0.05,
            c: 5.0,
            e: 121.0,
            expected: null,
        },
        {
            name: "index: decr past, then up",
            a: 0.4,
            b: -27.0,
            c: -480.0,
            e: 6400.0,
            expected: 9.211_646_096_066_227,
        },
        {
            name: "index: decr not reaching",
            a: 0.4,
            b: -6.0,
            c: 0.0,
            e: 6400.0,
            expected: null,
        },
        {
            name: "index: incr past next",
            a: 400.0,
            b: 920_000.0,
            c: 540_000_000.0,
            e: -32_400_000_000.0,
            expected: 54.767_996_111_769_335,
        },
        {
            name: "realistic: 1 day root",
            a: 1.0,
            b: -3.7,
            c: 4.55,
            e: -1.85,
            expected: 1.0,
        },
        {
            name: "realistic: 100-day root",
            a: 1.0,
            b: -200.0,
            c: 10_000.0,
            e: 0.0,
            expected: 100.0,
        },
    ];

    for (const c of cases) {
        test(c.name, () => {
            const got = findSmallestPositiveCubicRoot(c.a, c.b, c.c, c.e);
            if (c.expected === null) {
                expect(got).toBeNull();
            } else {
                expect(got).not.toBeNull();
                expect(Math.abs((got ?? 0) - c.expected)).toBeLessThan(
                    1e-6 * Math.max(1, c.expected),
                );
            }
        });
    }
});
