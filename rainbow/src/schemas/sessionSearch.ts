import { ALL_GAMEMODE_KEYS, ALL_STAT_KEYS } from "#stats/keys.ts";
import { z } from "zod";

export const sessionSearchSchema = z.object({
    timeIntervalDefinition: z
        .union([
            z.object({
                type: z.literal("contained"),
                date: z.coerce.date().optional().catch(undefined),
            }),
            z.object({
                type: z.literal("until"),
                date: z.coerce.date().optional().catch(undefined),
            }),
        ])
        .catch({ type: "contained" }),
    trackingStart: z.coerce
        .date()
        .optional()
        .catch(undefined)
        .transform((value) => {
            if (value === undefined) {
                return new Date(1970, 0, 1);
            }
            return value;
        }),
    gamemode: z.enum(ALL_GAMEMODE_KEYS).catch("overall"),
    stat: z.enum(ALL_STAT_KEYS).catch("fkdr"),
    variantSelection: z.enum(["session", "overall", "both"]).catch("both"),
    sessionTableMode: z.enum(["total", "rate"]).catch("total"),
    showExtrapolatedSessions: z.boolean().catch(false),
});
