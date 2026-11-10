import { z } from "zod";

import { computeWrappedYear } from "#helpers/wrapped.ts";

// `now` is injected so tests can pin "current time" deterministically. The real
// dependency is bound in the singleton export below, so consumers stay
// unchanged.
export const makeWrappedSearchSchema = (now: () => Date = () => new Date()) =>
    z.object({
        year: z.coerce
            .number()
            .int()
            .min(2025) // First full year with flashlight data from prism (started December 2024)
            // NOTE: This upper bound is frozen at schema-construction time.
            // Zod's `.max()` takes a plain value, not a thunk, so it cannot be
            // recomputed per parse the way `.catch`/`.default` can. In a
            // long-lived tab that crosses into a new wrapped year the bound goes
            // stale; the fallbacks below stay current, so the practical impact
            // is that a fresh-but-out-of-range year is rejected to the (also
            // fresh) fallback. Acceptable drift.
            .max(computeWrappedYear(now()))
            .catch(() => computeWrappedYear(now()))
            .default(() => computeWrappedYear(now())),
    });

export const wrappedSearchSchema = makeWrappedSearchSchema();
