import { z } from "zod";

import { startOfDay } from "#intervals.ts";
import { ALL_GAMEMODE_KEYS, ALL_STAT_KEYS } from "#stats/keys.ts";

// `now` is injected so tests can pin "current time" deterministically. The real
// dependency is bound in the singleton export below, so consumers stay
// unchanged. `trackingStart`'s default reads `now()` inside the transform, so
// it is recomputed on every parse rather than frozen at module-eval time.
export const makeSessionSearchSchema = (now: () => Date = () => new Date()) =>
    z.object({
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
                    // Default to start of day 1 year ago (same date). Copy the
                    // injected Date so we never mutate the caller's instance.
                    const date = new Date(now());
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

export const sessionSearchSchema = makeSessionSearchSchema();
