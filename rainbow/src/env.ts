import { z } from "zod";

const envSchema = z.object({
    // NOTE: The flashlight API does **not** allow third-party access.
    //       Do not send any requests to any endpoints without explicit permission.
    //       Reach out on Discord for more information. https://discord.gg/k4FGUnEHYg
    VITE_FLASHLIGHT_URL: z.url(),
    VITE_SENTRY_DSN: z.url().optional(),
});

const parse = (source: unknown) => {
    const env = envSchema.safeParse(source);
    if (!env.success) {
        // For better error messages when developing
        throw new Error(`Failed to parse environment: ${env.error.message}`);
    }
    return env.data;
};

// import.meta.env is not defined when running tests in node. Hacking it this way was the easiest fix I could think of without finding a whole new test runner
// eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
export const env = parse(import.meta.env ?? process.env);
