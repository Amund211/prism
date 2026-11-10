import { describe, expect, test } from "vitest";

import {
    BAD_STATS,
    getTrendDirection,
    getTrendSentiment,
    isBadStat,
} from "./format.ts";
import { ALL_STAT_KEYS } from "./keys.ts";

describe("isBadStat - good/bad classification", () => {
    test("bad stats are flagged", () => {
        for (const stat of BAD_STATS) {
            expect(isBadStat(stat)).toBe(true);
        }
    });

    test("every non-bad stat is good", () => {
        for (const stat of ALL_STAT_KEYS) {
            expect(isBadStat(stat)).toBe(BAD_STATS.includes(stat));
        }
    });

    // Literal tables, kept independent of BAD_STATS so the expectations don't
    // derive from the very constant under test. The good-stat table also guards
    // completeness: a newly added stat fails here until it's classified.
    test("exactly these stats are bad", () => {
        expect(
            ["deaths", "finalDeaths", "bedsLost", "losses"].toSorted(),
        ).toStrictEqual(ALL_STAT_KEYS.filter(isBadStat).toSorted());
    });

    test("every other stat is good", () => {
        expect(
            [
                "experience",
                "stars",
                "winstreak",
                "gamesPlayed",
                "wins",
                "bedsBroken",
                "finalKills",
                "kills",
                "fkdr",
                "kdr",
                "bblr",
                "wlr",
                "winrate",
                "index",
            ].toSorted(),
        ).toStrictEqual(ALL_STAT_KEYS.filter((stat) => !isBadStat(stat)).toSorted());
    });
});

describe("getTrendDirection - numeric movement", () => {
    test("classifies rising, falling, and flat movement", () => {
        expect(getTrendDirection(1, 2)).toBe("up");
        expect(getTrendDirection(2, 1)).toBe("down");
        expect(getTrendDirection(2, 2)).toBe("flat");
    });

    test("works with a diff against zero", () => {
        expect(getTrendDirection(0, 0.5)).toBe("up");
        expect(getTrendDirection(0, -0.5)).toBe("down");
        expect(getTrendDirection(0, 0)).toBe("flat");
    });
});

describe("getTrendSentiment - direction to good/bad", () => {
    test("flat movement is always neutral", () => {
        expect(getTrendSentiment("wins", "flat")).toBe("neutral");
        expect(getTrendSentiment("deaths", "flat")).toBe("neutral");
    });

    test("a rising good stat is good, a falling good stat is bad", () => {
        expect(getTrendSentiment("wins", "up")).toBe("good");
        expect(getTrendSentiment("wins", "down")).toBe("bad");
        expect(getTrendSentiment("fkdr", "up")).toBe("good");
        expect(getTrendSentiment("fkdr", "down")).toBe("bad");
    });

    test("a rising bad stat is bad, a falling bad stat is good", () => {
        expect(getTrendSentiment("deaths", "up")).toBe("bad");
        expect(getTrendSentiment("deaths", "down")).toBe("good");
        expect(getTrendSentiment("losses", "up")).toBe("bad");
        expect(getTrendSentiment("losses", "down")).toBe("good");
    });
});
