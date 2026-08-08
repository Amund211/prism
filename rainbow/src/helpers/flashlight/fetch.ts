import { captureException, captureMessage } from "@sentry/react";

import { env } from "#env.ts";
import { getOrSetUserId } from "#helpers/userId.ts";

// Client identification headers consumed by the flashlight backend. rainbow is
// evergreen (always served from the latest deploy), so it always reports the
// "evergreen" version. See https://github.com/Amund211/flashlight/pull/328.
//
// IMPORTANT: These headers identify us to flashlight and must ONLY be sent to
// the flashlight API. Do not attach them to requests to any other server.
const CLIENT_TYPE = "rainbow";
const CLIENT_VERSION = "evergreen";

// getFlashlightHeaders returns the headers to send with every request to the
// flashlight API. Centralizing them here keeps the client identification
// consistent across call sites and ensures they are only sent to flashlight.
export const getFlashlightHeaders = (): Record<string, string> => ({
    "X-User-Id": getOrSetUserId(),
    "X-Client-Type": CLIENT_TYPE,
    "X-Client-Version": CLIENT_VERSION,
});

type SentryExtra = Readonly<Record<string, unknown>>;

interface FlashlightFetchOptions {
    // Passed straight to fetch. The wrapper merges its own headers in and
    // forwards everything else untouched.
    readonly init?: Readonly<RequestInit>;
    // Prefix for the Sentry messages, e.g. "Failed to get history".
    readonly errorContext: string;
    // Call-site specific Sentry payload, attached to every report.
    readonly extra: SentryExtra;
}

/**
 * Fetch JSON from the flashlight API.
 *
 * NOTE: The flashlight API does **not** allow third-party access.
 *       Do not send any requests to any endpoints without explicit permission.
 *       Reach out on Discord for more information. https://discord.gg/k4FGUnEHYg
 */
export const flashlightFetch = async <T>(
    path: string,
    // RequestInit is not deeply readonly, and cannot be made so
    // oxlint-disable-next-line typescript/prefer-readonly-parameter-types
    { init, errorContext, extra }: FlashlightFetchOptions,
): Promise<T> => {
    const headers = new Headers(init?.headers);
    if (!headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
    }
    // Our headers always win: they identify the client to flashlight.
    for (const [name, value] of Object.entries(getFlashlightHeaders())) {
        headers.set(name, value);
    }

    const response = await fetch(`${env.VITE_FLASHLIGHT_URL}${path}`, {
        ...init,
        headers,
    }).catch((error: unknown) => {
        captureException(error, {
            extra: { ...extra, message: `${errorContext}: failed to fetch` },
        });
        throw error;
    });

    const tags = { status: response.status, statusText: response.statusText };

    // Read the body as text once, so both the error paths and the json parse
    // work off the same (single) read.
    const text = await response.text().catch((error: unknown) => {
        captureException(error, {
            tags,
            extra: {
                ...extra,
                message: `${errorContext}: failed to read response text`,
            },
        });
        throw error;
    });

    if (!response.ok) {
        captureMessage(`${errorContext}: response error`, {
            level: "error",
            tags,
            extra: { ...extra, ...tags, text },
        });
        throw new Error(
            `${errorContext}. ${response.status.toString()} - ${response.statusText}: ${text}`,
        );
    }

    try {
        return JSON.parse(text) as T;
    } catch (error: unknown) {
        captureException(error, {
            tags,
            extra: { ...extra, message: `${errorContext}: failed to parse json`, text },
        });
        throw error;
    }
};
