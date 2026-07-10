import { z } from "zod";

import { endOfDay, startOfDay } from "#intervals.ts";
import { ALL_GAMEMODE_KEYS, ALL_STAT_KEYS } from "#stats/keys.ts";

// `now` is injected so tests can pin "current time" deterministically. The real
// dependency is bound in the singleton export below, so consumers stay
// unchanged. The date fallbacks are thunks so "now" is recomputed on every
// parse rather than frozen at module-eval time.
export const makeHistoryExploreSearchSchema = (now: () => Date = () => new Date()) =>
    z.object({
        // TODO: Read "preferred user" from local storage or similar
        uuids: z.array(z.string()).readonly().catch([]).default([]),
        start: z.coerce
            .date()
            .catch(() => startOfDay(now()))
            .default(() => startOfDay(now())),
        end: z.coerce
            .date()
            .catch(() => endOfDay(now()))
            .default(() => endOfDay(now())),
        limit: z.number().int().min(1).max(50).catch(50).default(50),
        stats: z
            .enum(ALL_STAT_KEYS)
            .array()
            .readonly()
            .catch(["fkdr"])
            .default(["fkdr"]),
        gamemodes: z
            .enum(ALL_GAMEMODE_KEYS)
            .array()
            .readonly()
            .catch(["overall"])
            .default(["overall"]),
        variantSelection: z
            .enum(["session", "overall", "both"])
            .catch("session")
            .default("session"),
    });

export const historyExploreSearchSchema = makeHistoryExploreSearchSchema();
