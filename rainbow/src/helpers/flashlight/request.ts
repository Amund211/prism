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

// The server's "deal with your session now" hint, set on any response to a
// request that carried a valid bearer, from 5 minutes before it expires.
const REFRESH_HINT_HEADER = "X-Auth-Refresh";

export class FlashlightResponseError extends Error {
    public readonly status: number;

    public constructor(message: string, status: number) {
        super(message);
        this.name = "FlashlightResponseError";
        this.status = status;
    }
}

type SentryExtra = Readonly<Record<string, unknown>>;

export interface FlashlightRequestOptions {
    // Passed straight to fetch. The wrapper merges its own headers in and
    // forwards everything else untouched.
    readonly init?: Readonly<RequestInit>;
    // Prefix for the Sentry messages, e.g. "Failed to get history".
    readonly errorContext: string;
    // Call-site specific Sentry payload, attached to every report.
    readonly extra: SentryExtra;
    // Session id to send as a bearer, if any.
    readonly bearer?: string | undefined;
    // Statuses that are part of the protocol rather than a failure. Still
    // thrown, but not reported to Sentry.
    readonly expectedStatuses?: readonly number[];
}

export interface FlashlightResult<T> {
    readonly data: T;
    // Whether the response carried the refresh hint header.
    readonly refreshHint: boolean;
}

/**
 * Fetch JSON from the flashlight API, without any session handling.
 *
 * Callers outside of the auth endpoints want `flashlightFetch`, which adds the
 * bearer and the reactive re-auth on top of this.
 *
 * NOTE: The flashlight API does **not** allow third-party access.
 *       Do not send any requests to any endpoints without explicit permission.
 *       Reach out on Discord for more information. https://discord.gg/k4FGUnEHYg
 */
export const flashlightRequest = async <T>(
    path: string,
    // RequestInit is not deeply readonly, and cannot be made so
    // oxlint-disable-next-line typescript/prefer-readonly-parameter-types
    { init, errorContext, extra, bearer, expectedStatuses }: FlashlightRequestOptions,
): Promise<FlashlightResult<T>> => {
    const headers = new Headers(init?.headers);
    if (!headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
    }
    // Our headers always win: they identify the client to flashlight.
    for (const [name, value] of Object.entries(getFlashlightHeaders())) {
        headers.set(name, value);
    }
    if (bearer !== undefined) {
        headers.set("Authorization", `Bearer ${bearer}`);
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
    const refreshHint = response.headers.get(REFRESH_HINT_HEADER) === "1";

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
        if (expectedStatuses?.includes(response.status) !== true) {
            captureMessage(`${errorContext}: response error`, {
                level: "error",
                tags,
                extra: { ...extra, ...tags, text },
            });
        }
        throw new FlashlightResponseError(
            `${errorContext}. ${response.status.toString()} - ${response.statusText}: ${text}`,
            response.status,
        );
    }

    try {
        return { data: JSON.parse(text) as T, refreshHint };
    } catch (error: unknown) {
        captureException(error, {
            tags,
            extra: { ...extra, message: `${errorContext}: failed to parse json`, text },
        });
        throw error;
    }
};
