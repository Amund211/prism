import { z } from "zod";

// Fall back to the current time for a missing or malformed date so a shared or
// hand-edited link degrades to the NoSession view rather than tripping the
// router's error boundary. In-app links always pass a valid date.
//
// `now` is injected so tests can pin "current time" deterministically. The real
// dependency is bound in the singleton export below, so consumers stay
// unchanged. The fallbacks are thunks so "now" is recomputed on every parse
// rather than frozen at module-eval time.
export const makeDetailSearchSchema = (now: () => Date = () => new Date()) =>
    z.object({
        date: z.coerce
            .date()
            .catch(() => now())
            .default(() => now()),
    });

export const detailSearchSchema = makeDetailSearchSchema();
