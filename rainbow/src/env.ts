import { z } from "zod";

const envSchema = z.object({
    VITE_FLASHLIGHT_URL: z.string().url(),
    VITE_MOJANG_URL: z.string().url(),
});

const parse = (source: unknown) => {
    const env = envSchema.safeParse(source);
    if (!env.success) {
        // For better error messages when developing
        throw new Error(`Failed to parse environment ${env.error.toString()}`);
    }
    return env.data;
};

export const env = parse(import.meta.env);
