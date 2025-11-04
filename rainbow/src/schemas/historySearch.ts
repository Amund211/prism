import { ALL_GAMEMODE_KEYS, ALL_STAT_KEYS } from "#stats/keys.ts";
import { z } from "zod";

const defaultStart = new Date();
defaultStart.setHours(0, 0, 0, 0);
const defaultEnd = new Date();
defaultEnd.setHours(23, 59, 59, 999);

export const historyExploreSearchSchema = z.object({
    // TODO: Read "preferred user" from local storage or similar
    uuids: z.array(z.string()).readonly().catch([]),
    start: z.coerce.date().catch(defaultStart),
    end: z.coerce.date().catch(defaultEnd),
    limit: z.number().int().min(1).max(50).catch(50),
    stats: z.enum(ALL_STAT_KEYS).array().readonly().catch(["fkdr"]),
    gamemodes: z.enum(ALL_GAMEMODE_KEYS).array().readonly().catch(["overall"]),
    variantSelection: z.enum(["session", "overall", "both"]).catch("session"),
});
