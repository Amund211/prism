import { captureException } from "@sentry/react";

import { ensureSession } from "./auth/session.ts";
import { readSession } from "./auth/storage.ts";
import type { Session } from "./auth/storage.ts";
import { FlashlightResponseError, flashlightRequest } from "./request.ts";
import type { FlashlightRequestOptions, FlashlightResult } from "./request.ts";

type FlashlightFetchOptions = Omit<
    FlashlightRequestOptions,
    "bearer" | "expectedStatuses"
>;

const refreshInBackground = async (session: Session): Promise<void> => {
    try {
        await ensureSession(session);
    } catch (error: unknown) {
        captureException(error, {
            extra: { message: "Failed to act on the session refresh hint" },
        });
    }
};

// The refresh hint goes through the same single-flight promise as a 401 does: a
// six-query fan-out returns six copies of it, and each one must not become its
// own refresh.
const handleRefreshHint = <T>(result: FlashlightResult<T>, session: Session): T => {
    if (result.refreshHint) {
        void refreshInBackground(session);
    }
    return result.data;
};

/**
 * Fetch JSON from the flashlight API, authenticated with the current session.
 *
 * Reactive-only: fire the request with whatever session is stored, and on a 401
 * refresh (or log in again) and retry once.
 *
 * NOTE: The flashlight API does **not** allow third-party access.
 *       Do not send any requests to any endpoints without explicit permission.
 *       Reach out on Discord for more information. https://discord.gg/k4FGUnEHYg
 */
export const flashlightFetch = async <T>(
    path: string,
    // RequestInit is not deeply readonly, and cannot be made so
    // oxlint-disable-next-line typescript/prefer-readonly-parameter-types
    options: FlashlightFetchOptions,
): Promise<T> => {
    const session = readSession() ?? (await ensureSession(null));

    try {
        const result = await flashlightRequest<T>(path, {
            ...options,
            bearer: session.sessionId,
            // A lapsed session is the reactive path working as designed, not a
            // failure worth reporting.
            expectedStatuses: [401],
        });
        return handleRefreshHint(result, session);
    } catch (error: unknown) {
        if (!(error instanceof FlashlightResponseError) || error.status !== 401) {
            throw error;
        }

        // Re-sending the same init is only safe because every rainbow body is a
        // string (never a consumed stream) and none of these endpoints mutate
        // anything. An endpoint that streams a body, or one that writes, breaks
        // this retry silently.
        const next = await ensureSession(session);
        const result = await flashlightRequest<T>(path, {
            ...options,
            bearer: next.sessionId,
        });
        return handleRefreshHint(result, next);
    }
};
