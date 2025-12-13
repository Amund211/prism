import { getWrappedYear } from "#helpers/wrapped.ts";
import { z } from "zod";

const currentWrappedYear = getWrappedYear();

export const wrappedSearchSchema = z.object({
    year: z.coerce
        .number()
        .int()
        .min(2025) // First full year with flashlight data from prism (started December 2024)
        .max(currentWrappedYear)
        .catch(currentWrappedYear),
});
