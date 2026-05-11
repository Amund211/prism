import { z } from "zod";

import { startOfDay } from "#intervals.ts";
import { ALL_GAMEMODE_KEYS, ALL_STAT_KEYS } from "#stats/keys.ts";

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
        .catch({ type: "contained" })
        .default({ type: "contained" }),
    trackingStart: z.coerce
        .date()
        .optional()
        .catch(undefined)
        .transform((value) => {
            if (value === undefined) {
                // Default to start of day 1 year ago (same date)
                const date = new Date();
                date.setFullYear(date.getFullYear() - 1);
                return startOfDay(date);
            }
            return value;
        }),
    gamemode: z.enum(ALL_GAMEMODE_KEYS).catch("overall").default("overall"),
    stat: z.enum(ALL_STAT_KEYS).catch("fkdr").default("fkdr"),
    variantSelection: z
        .enum(["session", "overall", "both"])
        .catch("both")
        .default("both"),
    sessionTableMode: z.enum(["total", "rate"]).catch("total").default("total"),
    showExtrapolatedSessions: z.boolean().catch(false).default(false),
});
