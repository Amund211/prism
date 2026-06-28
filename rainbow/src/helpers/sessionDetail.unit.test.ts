import { describe, expect, test } from "vitest";

import type { PlayerDataPIT, StatsPIT } from "#queries/playerdata.ts";
import type {
    Gamemode,
    GameOutcome,
    GameResult,
    GameSegment,
} from "#queries/sessionAt.ts";
import type { Session } from "#queries/sessions.ts";
import { bedwarsLevelFromExp } from "#stats/stars.ts";

import type { ModeStats, SessionAggregate } from "./sessionDetail.ts";
import {
    aggregate,
    bestGame,
    computeMilestones,
    fastestWin,
    fkdrTrajectory,
    fkdrVsLifetime,
    gameAccolade,
    gameNumberLabel,
    inferredGameCount,
    isPerfectGame,
    modeBreakdown,
    segmentGameNumbers,
    sessionTagKeys,
    trailingStreak,
} from "./sessionDetail.ts";

const ZERO_STATS: StatsPIT = {
    winstreak: 0,
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

const PLACEHOLDER_PIT: PlayerDataPIT = {
    uuid: "00000000-0000-0000-0000-000000000000",
    queriedAt: new Date(1_700_000_000_000),
    experience: 0,
    solo: ZERO_STATS,
    doubles: ZERO_STATS,
    threes: ZERO_STATS,
    fours: ZERO_STATS,
    "4v4": ZERO_STATS,
    overall: ZERO_STATS,
};

const makeStats = (overrides: Partial<StatsPIT>): StatsPIT => ({
    ...ZERO_STATS,
    ...overrides,
});

const makePIT = (overrides: Partial<PlayerDataPIT>): PlayerDataPIT => ({
    ...PLACEHOLDER_PIT,
    ...overrides,
});

const makeSession = (start: PlayerDataPIT, end: PlayerDataPIT): Session => ({
    start,
    end,
    extrapolated: false,
    consecutive: true,
    ongoing: false,
});

const makeGame = (overrides: Partial<GameResult>): GameResult => ({
    gamemode: "fours",
    outcome: "win",
    finalKills: 0,
    finalDeath: false,
    bedsBroken: 0,
    bedLost: false,
    kills: 0,
    deaths: 0,
    experience: 0,
    ...overrides,
});

const makeSegment = (
    game: GameResult | null,
    start: PlayerDataPIT = PLACEHOLDER_PIT,
    end: PlayerDataPIT = PLACEHOLDER_PIT,
): GameSegment => ({ start, end, game });

describe(bestGame, () => {
    const cases: {
        name: string;
        // null = an ambiguous (no-game / multi-game) segment
        games: (Partial<GameResult> | null)[];
        // index of the expected best segment, or null when none
        expected: number | null;
    }[] = [
        { name: "no segments", games: [], expected: null },
        { name: "only ambiguous segments", games: [null, null], expected: null },
        { name: "single game", games: [{ finalKills: 3 }], expected: 0 },
        {
            name: "picks the most final kills",
            games: [{ finalKills: 2 }, { finalKills: 5 }, { finalKills: 4 }],
            expected: 1,
        },
        {
            name: "skips ambiguous segments",
            games: [{ finalKills: 5 }, null, { finalKills: 3 }],
            expected: 0,
        },
        {
            name: "final kills beat a cleaner game with fewer kills",
            games: [
                { finalKills: 6, finalDeath: true },
                { finalKills: 5, finalDeath: false },
            ],
            expected: 0,
        },
        {
            name: "tie on kills breaks toward no final death",
            games: [
                { finalKills: 5, finalDeath: true },
                { finalKills: 5, finalDeath: false },
            ],
            expected: 1,
        },
        {
            name: "tie on kills + final death breaks toward no bed lost",
            games: [
                { finalKills: 5, finalDeath: true, bedLost: true },
                { finalKills: 5, finalDeath: true, bedLost: false },
            ],
            expected: 1,
        },
        {
            name: "full tie keeps the earliest game",
            games: [
                { finalKills: 5, finalDeath: false, bedLost: false },
                { finalKills: 5, finalDeath: false, bedLost: false },
            ],
            expected: 0,
        },
    ];

    test.each(cases)("$name", ({ games, expected }) => {
        const segments = games.map((game) =>
            makeSegment(game === null ? null : makeGame(game)),
        );
        const result = bestGame(segments);
        if (expected === null) {
            expect(result).toBeUndefined();
        } else {
            expect(result).toBe(segments[expected]);
        }
    });
});

describe(fastestWin, () => {
    // Each spec is [outcome | null (= gap), durationMinutes].
    const segOf = ([outcome, mins]: readonly [
        GameOutcome | null,
        number,
    ]): GameSegment =>
        makeSegment(
            outcome === null ? null : makeGame({ outcome }),
            makePIT({ queriedAt: new Date(0) }),
            makePIT({ queriedAt: new Date(mins * 60_000) }),
        );

    const cases: {
        name: string;
        segs: [GameOutcome | null, number][];
        expected: number | null;
    }[] = [
        { name: "no segments", segs: [], expected: null },
        {
            name: "no wins",
            segs: [
                ["loss", 5],
                [null, 3],
            ],
            expected: null,
        },
        {
            name: "picks the shortest win",
            segs: [
                ["win", 10],
                ["win", 4],
                ["win", 7],
            ],
            expected: 1,
        },
        {
            name: "ignores losses and gaps",
            segs: [
                ["loss", 1],
                [null, 2],
                ["win", 8],
            ],
            expected: 2,
        },
        {
            name: "tie on duration keeps the earliest win",
            segs: [
                ["win", 5],
                ["win", 5],
            ],
            expected: 0,
        },
    ];

    test.each(cases)("$name", ({ segs, expected }) => {
        const segments = segs.map(segOf);
        const result = fastestWin(segments);
        if (expected === null) {
            expect(result).toBeUndefined();
        } else {
            expect(result).toBe(segments[expected]);
        }
    });
});

describe(trailingStreak, () => {
    const cases: {
        name: string;
        // null = an ambiguous segment (breaks the streak)
        outcomes: (GameOutcome | null)[];
        expected: { length: number; outcome: GameOutcome } | null;
    }[] = [
        { name: "empty", outcomes: [], expected: null },
        { name: "single game is not a streak", outcomes: ["win"], expected: null },
        {
            name: "two trailing wins",
            outcomes: ["win", "win"],
            expected: { length: 2, outcome: "win" },
        },
        {
            name: "counts only the trailing run",
            outcomes: ["loss", "win", "win", "win"],
            expected: { length: 3, outcome: "win" },
        },
        {
            name: "an opposite result breaks the streak",
            outcomes: ["win", "loss", "win"],
            expected: null,
        },
        {
            name: "a gap breaks the streak",
            outcomes: ["win", null, "win", "win"],
            expected: { length: 2, outcome: "win" },
        },
        {
            name: "a trailing gap means no streak",
            outcomes: ["win", "win", null],
            expected: null,
        },
        {
            name: "all losses",
            outcomes: ["loss", "loss", "loss"],
            expected: { length: 3, outcome: "loss" },
        },
        {
            name: "draws form a streak internally",
            outcomes: ["draw", "draw"],
            expected: { length: 2, outcome: "draw" },
        },
    ];

    test.each(cases)("$name", ({ outcomes, expected }) => {
        const segments = outcomes.map((outcome) =>
            makeSegment(outcome === null ? null : makeGame({ outcome })),
        );
        expect(trailingStreak(segments)).toStrictEqual(expected);
    });
});

describe(inferredGameCount, () => {
    // The count must come from `overall`, not the core modes — games in a
    // non-core mode (a Dreams mode) move overall but leave the core modes flat.
    const pit = (
        overall: number,
        core: Partial<Record<Gamemode, number>> = {},
    ): PlayerDataPIT =>
        makePIT({
            overall: makeStats({ gamesPlayed: overall }),
            solo: makeStats({ gamesPlayed: core.solo ?? 0 }),
            doubles: makeStats({ gamesPlayed: core.doubles ?? 0 }),
            threes: makeStats({ gamesPlayed: core.threes ?? 0 }),
            fours: makeStats({ gamesPlayed: core.fours ?? 0 }),
        });

    const cases: {
        name: string;
        start: { overall: number; core?: Partial<Record<Gamemode, number>> };
        end: { overall: number; core?: Partial<Record<Gamemode, number>> };
        expected: number;
    }[] = [
        {
            name: "no games played",
            start: { overall: 0 },
            end: { overall: 0 },
            expected: 0,
        },
        {
            name: "a single game",
            start: { overall: 10 },
            end: { overall: 11 },
            expected: 1,
        },
        {
            name: "a multi-game jump",
            start: { overall: 10 },
            end: { overall: 12 },
            expected: 2,
        },
        {
            name: "counts non-core games where the core modes stay flat",
            start: { overall: 25_234, core: {} },
            end: { overall: 25_236, core: {} },
            expected: 2,
        },
        {
            name: "ignores a decrease",
            start: { overall: 5 },
            end: { overall: 3 },
            expected: 0,
        },
    ];

    test.each(cases)("$name", ({ start, end, expected }) => {
        const segment = makeSegment(
            null,
            pit(start.overall, start.core),
            pit(end.overall, end.core),
        );
        expect(inferredGameCount(segment)).toBe(expected);
    });
});

describe(aggregate, () => {
    test("computes deltas, ratios, xp, stars and elapsed time", () => {
        const start = makePIT({
            experience: 1_000_000,
            queriedAt: new Date(1_700_000_000_000),
            overall: makeStats({
                gamesPlayed: 100,
                wins: 60,
                losses: 40,
                finalKills: 200,
                finalDeaths: 50,
                bedsBroken: 80,
                bedsLost: 30,
                kills: 500,
                deaths: 300,
            }),
        });
        const end = makePIT({
            experience: 1_100_000,
            queriedAt: new Date(1_700_000_000_000 + 3_600_000),
            overall: makeStats({
                gamesPlayed: 110,
                wins: 66,
                losses: 44,
                finalKills: 230,
                finalDeaths: 60,
                bedsBroken: 90,
                bedsLost: 35,
                kills: 560,
                deaths: 330,
            }),
        });

        expect(aggregate(makeSession(start, end))).toStrictEqual({
            games: 10,
            wins: 6,
            losses: 4,
            fk: 30,
            fd: 10,
            bb: 10,
            bl: 5,
            k: 60,
            d: 30,
            xp: 100_000,
            stars: bedwarsLevelFromExp(1_100_000) - bedwarsLevelFromExp(1_000_000),
            fkdr: 3,
            lifetimeFkdr: 4,
            winRate: 0.6,
            lifetimeWR: 0.6,
            elapsedMs: 3_600_000,
        });
    });

    test("ratios fall back to the numerator when the denominator is zero", () => {
        const start = makePIT({ overall: ZERO_STATS });
        const end = makePIT({
            overall: makeStats({
                gamesPlayed: 5,
                wins: 5,
                finalKills: 12,
                finalDeaths: 0,
            }),
        });

        const result = aggregate(makeSession(start, end));
        // No final deaths this session -> FKDR is just the final kills.
        expect(result.fkdr).toBe(12);
        // No lifetime games yet -> lifetime ratios are their numerators (0).
        expect(result.lifetimeFkdr).toBe(0);
        expect(result.lifetimeWR).toBe(0);
        expect(result.winRate).toBe(1);
    });
});

describe(modeBreakdown, () => {
    const ZERO_MODE: ModeStats = {
        games: 0,
        wins: 0,
        losses: 0,
        winRate: 0,
        fk: 0,
        fd: 0,
        fkdr: 0,
        bb: 0,
        bl: 0,
        k: 0,
        d: 0,
        kdr: 0,
    };

    test("computes per-mode deltas and ratios, leaving unplayed modes at zero", () => {
        const start = makePIT({
            // overall must cover the core modes (here: just doubles' 10 games).
            overall: makeStats({
                gamesPlayed: 10,
                wins: 6,
                losses: 4,
                finalKills: 20,
                finalDeaths: 10,
                bedsBroken: 8,
                bedsLost: 3,
                kills: 50,
                deaths: 30,
            }),
            doubles: makeStats({
                gamesPlayed: 10,
                wins: 6,
                losses: 4,
                finalKills: 20,
                finalDeaths: 10,
                bedsBroken: 8,
                bedsLost: 3,
                kills: 50,
                deaths: 30,
            }),
        });
        const end = makePIT({
            // overall delta = doubles delta + threes delta exactly -> no "other".
            overall: makeStats({
                gamesPlayed: 13,
                wins: 8,
                losses: 5,
                finalKills: 31,
                finalDeaths: 12,
                bedsBroken: 10,
                bedsLost: 4,
                kills: 60,
                deaths: 33,
            }),
            doubles: makeStats({
                gamesPlayed: 12,
                wins: 7,
                losses: 5,
                finalKills: 26,
                finalDeaths: 12,
                bedsBroken: 10,
                bedsLost: 4,
                kills: 60,
                deaths: 33,
            }),
            // No final deaths in threes -> FKDR falls back to final kills.
            threes: makeStats({
                gamesPlayed: 1,
                wins: 1,
                finalKills: 5,
                finalDeaths: 0,
            }),
        });

        const data = modeBreakdown(makeSession(start, end));

        expect(data.doubles).toStrictEqual({
            games: 2,
            wins: 1,
            losses: 1,
            winRate: 0.5,
            fk: 6,
            fd: 2,
            fkdr: 3,
            bb: 2,
            bl: 1,
            k: 10,
            d: 3,
            kdr: 10 / 3,
        });
        expect(data.threes).toStrictEqual({
            games: 1,
            wins: 1,
            losses: 0,
            winRate: 1,
            fk: 5,
            fd: 0,
            fkdr: 5,
            bb: 0,
            bl: 0,
            k: 0,
            d: 0,
            kdr: 0,
        });
        expect(data.solo).toStrictEqual(ZERO_MODE);
        expect(data.fours).toStrictEqual(ZERO_MODE);
        expect(data["4v4"]).toStrictEqual(ZERO_MODE);
        // overall delta exactly equals the core modes -> nothing left over.
        expect(data.other).toStrictEqual(ZERO_MODE);
    });

    test("attributes overall games not in the core modes to the other bucket", () => {
        const start = makePIT({ overall: ZERO_STATS });
        const end = makePIT({
            // 2 wins / +715 xp worth of games, none of them in a core mode —
            // the core modes stay flat, overall moves. Mirrors the prod session.
            overall: makeStats({ gamesPlayed: 2, wins: 2, losses: 0 }),
        });

        const data = modeBreakdown(makeSession(start, end));

        expect(data.solo).toStrictEqual(ZERO_MODE);
        expect(data.doubles).toStrictEqual(ZERO_MODE);
        expect(data.threes).toStrictEqual(ZERO_MODE);
        expect(data.fours).toStrictEqual(ZERO_MODE);
        expect(data["4v4"]).toStrictEqual(ZERO_MODE);
        expect(data.other).toStrictEqual({
            games: 2,
            wins: 2,
            losses: 0,
            winRate: 1,
            fk: 0,
            fd: 0,
            fkdr: 0,
            bb: 0,
            bl: 0,
            k: 0,
            d: 0,
            kdr: 0,
        });
    });

    test("gives 4v4 its own tile instead of the other bucket", () => {
        const start = makePIT({ overall: ZERO_STATS });
        const end = makePIT({
            // A 4v4-only session: overall and 4v4 move in lockstep, so the
            // whole delta is attributed to 4v4 and nothing is left over.
            overall: makeStats({
                gamesPlayed: 3,
                wins: 2,
                losses: 1,
                finalKills: 6,
                finalDeaths: 2,
                bedsBroken: 2,
                bedsLost: 1,
                kills: 9,
                deaths: 3,
            }),
            "4v4": makeStats({
                gamesPlayed: 3,
                wins: 2,
                losses: 1,
                finalKills: 6,
                finalDeaths: 2,
                bedsBroken: 2,
                bedsLost: 1,
                kills: 9,
                deaths: 3,
            }),
        });

        const data = modeBreakdown(makeSession(start, end));

        expect(data["4v4"]).toStrictEqual({
            games: 3,
            wins: 2,
            losses: 1,
            winRate: 2 / 3,
            fk: 6,
            fd: 2,
            fkdr: 3,
            bb: 2,
            bl: 1,
            k: 9,
            d: 3,
            kdr: 3,
        });
        expect(data.solo).toStrictEqual(ZERO_MODE);
        expect(data.doubles).toStrictEqual(ZERO_MODE);
        expect(data.threes).toStrictEqual(ZERO_MODE);
        expect(data.fours).toStrictEqual(ZERO_MODE);
        expect(data.other).toStrictEqual(ZERO_MODE);
    });
});

describe(fkdrTrajectory, () => {
    const start = makePIT({
        overall: makeStats({ finalKills: 10, finalDeaths: 5 }),
    });
    const session = makeSession(start, PLACEHOLDER_PIT);

    // A real single-game segment ending at the given overall finals.
    const realSeg = (finalKills: number, finalDeaths: number): GameSegment =>
        makeSegment(
            makeGame({}),
            PLACEHOLDER_PIT,
            makePIT({ overall: makeStats({ finalKills, finalDeaths }) }),
        );

    // A gap segment (no attributable per-game stats) covering
    // `endGames - startGames` games.
    const gapSeg = (
        startGames: number,
        endGames: number,
        finalKills: number,
        finalDeaths: number,
    ): GameSegment =>
        makeSegment(
            null,
            makePIT({ overall: makeStats({ gamesPlayed: startGames }) }),
            makePIT({
                overall: makeStats({ gamesPlayed: endGames, finalKills, finalDeaths }),
            }),
        );

    test("returns no points for an empty session", () => {
        expect(fkdrTrajectory(session, [])).toStrictEqual([]);
    });

    test("numbers real games sequentially and tracks session vs lifetime FKDR", () => {
        const segments = [
            realSeg(20, 10), // session (10/5)=2,  lifetime (20/10)=2
            realSeg(40, 10), // session (30/5)=6,  lifetime (40/10)=4
            realSeg(15, 5), // session (5/0)=5 (no deaths), lifetime (15/5)=3
        ];

        expect(fkdrTrajectory(session, segments)).toStrictEqual([
            { label: "G1", sessionFkdr: 2, lifetimeFkdr: 2 },
            { label: "G2", sessionFkdr: 6, lifetimeFkdr: 4 },
            { label: "G3", sessionFkdr: 5, lifetimeFkdr: 3 },
        ]);
    });

    test("labels a multi-game gap with the range of games it spans", () => {
        const segments = [
            realSeg(20, 10), // G1
            gapSeg(100, 103, 50, 20), // 3 games -> G2-4
        ];

        expect(fkdrTrajectory(session, segments)).toStrictEqual([
            { label: "G1", sessionFkdr: 2, lifetimeFkdr: 2 },
            { label: "G2-4", sessionFkdr: 40 / 15, lifetimeFkdr: 2.5 },
        ]);
    });

    test("drops no-game windows and keeps the numbering across them", () => {
        const segments = [
            realSeg(20, 10), // G1
            gapSeg(100, 100, 30, 12), // no games played -> excluded
            realSeg(40, 10), // G2 (the dropped window didn't advance the count)
        ];

        expect(fkdrTrajectory(session, segments)).toStrictEqual([
            { label: "G1", sessionFkdr: 2, lifetimeFkdr: 2 },
            { label: "G2", sessionFkdr: 6, lifetimeFkdr: 4 },
        ]);
    });
});

describe(segmentGameNumbers, () => {
    const real = (): GameSegment => makeSegment(makeGame({}));
    // A gap covering `games` games (0 => a no-game window).
    const gap = (games: number): GameSegment =>
        makeSegment(
            null,
            makePIT({ overall: makeStats({ gamesPlayed: 0 }) }),
            makePIT({ overall: makeStats({ gamesPlayed: games }) }),
        );

    test("returns nothing for an empty session", () => {
        expect(segmentGameNumbers([])).toStrictEqual([]);
    });

    test("numbers consecutive real games sequentially", () => {
        expect(segmentGameNumbers([real(), real(), real()])).toStrictEqual([
            { first: 1, last: 1, count: 1 },
            { first: 2, last: 2, count: 1 },
            { first: 3, last: 3, count: 1 },
        ]);
    });

    test("a no-game window has no number and doesn't advance the count", () => {
        expect(segmentGameNumbers([real(), gap(0), real()])).toStrictEqual([
            { first: 1, last: 1, count: 1 },
            { first: null, last: null, count: 0 },
            { first: 2, last: 2, count: 1 },
        ]);
    });

    test("a multi-game gap spans the range of games it covers", () => {
        expect(segmentGameNumbers([real(), gap(3), real()])).toStrictEqual([
            { first: 1, last: 1, count: 1 },
            { first: 2, last: 4, count: 3 },
            { first: 5, last: 5, count: 1 },
        ]);
    });

    test("a single unattributable game still gets one number", () => {
        expect(segmentGameNumbers([gap(1), real()])).toStrictEqual([
            { first: 1, last: 1, count: 1 },
            { first: 2, last: 2, count: 1 },
        ]);
    });
});

describe(gameNumberLabel, () => {
    const cases: {
        name: string;
        num: { first: number | null; last: number | null; count: number };
        expected: string | null;
    }[] = [
        { name: "single game", num: { first: 3, last: 3, count: 1 }, expected: "G3" },
        {
            name: "multi-game gap",
            num: { first: 5, last: 7, count: 3 },
            expected: "G5-7",
        },
        {
            name: "no-game window",
            num: { first: null, last: null, count: 0 },
            expected: null,
        },
    ];

    test.each(cases)("$name", ({ num, expected }) => {
        expect(gameNumberLabel(num)).toBe(expected);
    });
});

describe(computeMilestones, () => {
    const HOUR_MS = 60 * 60 * 1000;
    const T0 = 1_700_000_000_000;

    // A one-hour session with progress on every tracked stat, so all three
    // milestones are reachable.
    const progressingSession = (): Session => {
        const start = makePIT({
            queriedAt: new Date(T0),
            experience: 1_000_000,
            overall: makeStats({
                gamesPlayed: 500,
                wins: 300,
                losses: 200,
                finalKills: 750,
                finalDeaths: 250,
            }),
        });
        const end = makePIT({
            queriedAt: new Date(T0 + HOUR_MS),
            experience: 1_100_000,
            overall: makeStats({
                gamesPlayed: 520,
                wins: 315,
                losses: 205,
                finalKills: 810,
                finalDeaths: 260,
            }),
        });
        return makeSession(start, end);
    };

    const milestonesByKey = (session: Session) => {
        const agg = aggregate(session);
        const milestones = computeMilestones(session, agg);
        return {
            agg,
            milestones,
            prestige: milestones.find((m) => m.key === "prestige"),
            wins: milestones.find((m) => m.key === "wins"),
            fkdr: milestones.find((m) => m.key === "fkdr"),
        };
    };

    test("returns the prestige, wins and fkdr milestones in order", () => {
        const session = progressingSession();
        const milestones = computeMilestones(session, aggregate(session));

        expect(milestones.map((m) => m.key)).toStrictEqual([
            "prestige",
            "wins",
            "fkdr",
        ]);
        expect(milestones.map((m) => m.label)).toStrictEqual([
            "Next stars milestone",
            "Next wins milestone",
            "Next FKDR milestone",
        ]);
    });

    test("projects a reachable counter milestone with finite pace", () => {
        const { wins, agg } = milestonesByKey(progressingSession());

        // +15 wins in the hour -> next half-decade above 315 is 350.
        expect(wins?.current).toBe(315);
        expect(wins?.target).toBe(350);
        expect(wins?.blockedReason).toBeNull();
        // (350-315) at 15 wins/session -> 2h20m of play.
        expect(wins?.playtimeMs).toBeCloseTo(8_400_000);
        expect(Number.isFinite(wins?.sessions ?? Infinity)).toBe(true);
        // `sessions` is the projected playtime measured in session-lengths.
        expect((wins?.sessions ?? 0) * agg.elapsedMs).toBeCloseTo(
            wins?.playtimeMs ?? 0,
        );
        expect(wins?.deltaFormat()).toBe("+15/session");
    });

    test("projects the fkdr milestone from the session's kill ratio", () => {
        const { fkdr } = milestonesByKey(progressingSession());

        // End fkdr 810/260 ≈ 3.115; next 0.5 step up is 3.5.
        expect(fkdr?.current).toBeCloseTo(810 / 260);
        expect(fkdr?.target).toBe(3.5);
        expect(fkdr?.blockedReason).toBeNull();
        expect(fkdr?.playtimeMs).toBeCloseTo(14_400_000);
        expect(fkdr?.sessions).toBeCloseTo(4);
    });

    test("reports the prestige milestone from experience gained", () => {
        const session = progressingSession();
        const { prestige } = milestonesByKey(session);
        const endStars = bedwarsLevelFromExp(session.end.experience);

        expect(prestige?.current).toBeCloseTo(endStars);
        // Next multiple of ten (a tenth of a prestige) above the current stars.
        expect(prestige?.target).toBe((Math.floor(endStars / 10) + 1) * 10);
        expect(prestige?.blockedReason).toBeNull();
        expect(Number.isFinite(prestige?.sessions ?? Infinity)).toBe(true);
        expect(prestige?.playtimeMs ?? 0).toBeGreaterThan(0);
    });

    test("blocks a counter milestone when no progress was made on it", () => {
        // Wins stay flat while finals climb: the wins milestone has no pace.
        const start = makePIT({
            queriedAt: new Date(T0),
            experience: 1_000_000,
            overall: makeStats({
                gamesPlayed: 500,
                wins: 300,
                losses: 200,
                finalKills: 750,
                finalDeaths: 250,
            }),
        });
        const end = makePIT({
            queriedAt: new Date(T0 + HOUR_MS),
            experience: 1_050_000,
            overall: makeStats({
                gamesPlayed: 510,
                wins: 300, // unchanged
                losses: 210,
                finalKills: 800,
                finalDeaths: 260,
            }),
        });

        const { wins } = milestonesByKey(makeSession(start, end));

        expect(wins?.target).toBeNull();
        expect(wins?.sessions).toBe(Number.POSITIVE_INFINITY);
        expect(wins?.playtimeMs).toBe(0);
        expect(wins?.blockedReason).toBe("No progress this session");
        // Falls back to the raw end-of-session count when there's no projection.
        expect(wins?.current).toBe(300);
    });

    test("shows an off-pace milestone's target but no reachable pace", () => {
        // Experience is flat, so the stars milestone is projected but never
        // reached: the target is still shown, the pace is infinite.
        const start = makePIT({
            queriedAt: new Date(T0),
            experience: 1_000_000,
            overall: makeStats({
                gamesPlayed: 500,
                wins: 300,
                finalKills: 750,
                finalDeaths: 250,
            }),
        });
        const end = makePIT({
            queriedAt: new Date(T0 + HOUR_MS),
            experience: 1_000_000, // unchanged -> no stars pace
            overall: makeStats({
                gamesPlayed: 520,
                wins: 315,
                finalKills: 810,
                finalDeaths: 260,
            }),
        });
        const session = makeSession(start, end);

        const { prestige } = milestonesByKey(session);

        expect(prestige?.target).not.toBeNull();
        expect(prestige?.sessions).toBe(Number.POSITIVE_INFINITY);
        expect(prestige?.playtimeMs).toBe(0);
        expect(prestige?.blockedReason).toBe("Not on pace to reach this");
        expect(prestige?.current).toBeCloseTo(
            bedwarsLevelFromExp(session.end.experience),
        );
    });
});

const ZERO_AGG: SessionAggregate = {
    games: 0,
    wins: 0,
    losses: 0,
    fk: 0,
    fd: 0,
    bb: 0,
    bl: 0,
    k: 0,
    d: 0,
    xp: 0,
    stars: 0,
    fkdr: 0,
    lifetimeFkdr: 0,
    winRate: 0,
    lifetimeWR: 0,
    elapsedMs: 0,
};

const makeAgg = (overrides: Partial<SessionAggregate>): SessionAggregate => ({
    ...ZERO_AGG,
    ...overrides,
});

describe(sessionTagKeys, () => {
    const HOUR_MS = 60 * 60 * 1000;
    const cases: {
        name: string;
        agg: Partial<SessionAggregate>;
        expected: string[];
    }[] = [
        {
            name: "an unremarkable session earns nothing",
            agg: { games: 1 },
            expected: [],
        },
        {
            name: "flawless: 2+ games, no losses, no final deaths",
            agg: { games: 2, losses: 0, fd: 0 },
            expected: ["flawless"],
        },
        {
            name: "flawless beats perfect when both would apply",
            agg: { games: 5, losses: 0, fd: 0 },
            expected: ["flawless"],
        },
        {
            name: "perfect: 3+ wins but took a final death",
            agg: { games: 3, wins: 3, losses: 0, fd: 1 },
            expected: ["perfect"],
        },
        {
            name: "not perfect when a draw means not every game was won",
            agg: { games: 3, wins: 2, losses: 0, fd: 1 },
            expected: [],
        },
        {
            name: "neither flawless nor perfect with only 2 games and a final death",
            agg: { games: 2, losses: 0, fd: 1 },
            expected: [],
        },
        {
            name: "on_fire: FKDR well above lifetime with enough finals",
            agg: { games: 1, losses: 1, fkdr: 3, lifetimeFkdr: 2, fk: 6 },
            expected: ["on_fire"],
        },
        {
            name: "on_fire needs at least 6 final kills",
            agg: { games: 1, losses: 1, fkdr: 3, lifetimeFkdr: 2, fk: 5 },
            expected: [],
        },
        {
            name: "marathon: at least three hours played",
            agg: { games: 1, losses: 1, elapsedMs: 3 * HOUR_MS },
            expected: ["marathon"],
        },
        {
            name: "tags stack",
            agg: {
                games: 4,
                losses: 0,
                fd: 0,
                fkdr: 10,
                lifetimeFkdr: 2,
                fk: 8,
                elapsedMs: 4 * HOUR_MS,
            },
            expected: ["flawless", "on_fire", "marathon"],
        },
    ];

    test.each(cases)("$name", ({ agg, expected }) => {
        expect(sessionTagKeys(makeAgg(agg))).toStrictEqual(expected);
    });
});

describe(fkdrVsLifetime, () => {
    const cases: {
        name: string;
        agg: Partial<SessionAggregate>;
        expected: "beating" | "on_par" | "below";
    }[] = [
        {
            name: "clearly above",
            agg: { fkdr: 2, lifetimeFkdr: 1 },
            expected: "beating",
        },
        {
            name: "clearly below",
            agg: { fkdr: 0.5, lifetimeFkdr: 1 },
            expected: "below",
        },
        {
            name: "within the band",
            agg: { fkdr: 1.05, lifetimeFkdr: 1 },
            expected: "on_par",
        },
        {
            name: "exactly +10% is beating",
            agg: { fkdr: 1.1, lifetimeFkdr: 1 },
            expected: "beating",
        },
        {
            name: "exactly -10% is below",
            agg: { fkdr: 0.9, lifetimeFkdr: 1 },
            expected: "below",
        },
        {
            name: "no lifetime finals but positive session FKDR is beating",
            agg: { fkdr: 3, lifetimeFkdr: 0 },
            expected: "beating",
        },
        {
            name: "no lifetime finals and no session finals is on par",
            agg: { fkdr: 0, lifetimeFkdr: 0 },
            expected: "on_par",
        },
    ];

    test.each(cases)("$name", ({ agg, expected }) => {
        expect(fkdrVsLifetime(makeAgg(agg))).toBe(expected);
    });
});

describe(isPerfectGame, () => {
    const cases: {
        name: string;
        game: Partial<GameResult>;
        expected: boolean;
    }[] = [
        {
            name: "fours: both thresholds met",
            game: { gamemode: "fours", finalKills: 16, bedsBroken: 3 },
            expected: true,
        },
        {
            name: "fours: one bed short",
            game: { gamemode: "fours", finalKills: 16, bedsBroken: 2 },
            expected: false,
        },
        {
            name: "fours: one final short",
            game: { gamemode: "fours", finalKills: 15, bedsBroken: 3 },
            expected: false,
        },
        {
            name: "exceeding the thresholds still counts",
            game: { gamemode: "fours", finalKills: 20, bedsBroken: 5 },
            expected: true,
        },
        {
            name: "solo thresholds",
            game: { gamemode: "solo", finalKills: 7, bedsBroken: 7 },
            expected: true,
        },
        {
            name: "4v4 thresholds",
            game: { gamemode: "4v4", finalKills: 4, bedsBroken: 1 },
            expected: true,
        },
    ];

    test.each(cases)("$name", ({ game, expected }) => {
        expect(isPerfectGame(makeGame(game))).toBe(expected);
    });
});

describe(gameAccolade, () => {
    const cases: {
        name: string;
        game: Partial<GameResult>;
        expected: "perfect" | "carried" | "clutch" | null;
    }[] = [
        { name: "a loss has no accolade", game: { outcome: "loss" }, expected: null },
        { name: "a draw has no accolade", game: { outcome: "draw" }, expected: null },
        {
            name: "perfect game wins outright",
            game: {
                gamemode: "fours",
                finalKills: 16,
                bedsBroken: 3,
                finalDeath: true,
            },
            expected: "perfect",
        },
        {
            name: "carried: won after a final death",
            game: { finalDeath: true, bedLost: true },
            expected: "carried",
        },
        {
            name: "clutch: won after losing the bed (no final death)",
            game: { finalDeath: false, bedLost: true },
            expected: "clutch",
        },
        {
            name: "an unremarkable win has no accolade",
            game: { finalDeath: false, bedLost: false },
            expected: null,
        },
    ];

    test.each(cases)("$name", ({ game, expected }) => {
        expect(gameAccolade(makeGame(game))).toBe(expected);
    });
});
