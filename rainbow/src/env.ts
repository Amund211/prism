import { z } from "zod";

const envSchema = z.object({
    VITE_FLASHLIGHT_URL: z.string().url(),
    VITE_MINETOOLS_API_URL: z.string().url(),
    VITE_SENTRY_DSN: z.string(),
});

const parse = (source: unknown) => {
    const env = envSchema.safeParse(source);
    if (!env.success) {
        // For better error messages when developing
        throw new Error(`Failed to parse environment ${env.error.toString()}`);
    }
    return env.data;
};

// import.meta.env is not defined when running tests in node. Hacking it this way was the easiest fix I could think of without finding a whole new test runner
// eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
export const env = parse(import.meta.env ?? process.env);
