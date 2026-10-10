import { captureMessage } from "@sentry/react";

import {
    FlashlightResponseError,
    flashlightRequest,
} from "#helpers/flashlight/request.ts";

import type { Challenge } from "./proofOfWork.ts";
import { isTier, validateSessionId, withUUID } from "./storage.ts";
import type { Session } from "./storage.ts";

export interface APIChallengeResponse {
    readonly challenge: string;
    readonly algorithm: string;
    readonly difficulty: number;
    readonly expiresInSeconds: number;
}

export interface APISessionResponse {
    readonly sessionId: string;
    readonly tier: string;
    readonly expiresInSeconds: number;
    readonly refreshUntilInSeconds: number;
    readonly refreshInSeconds: number;
    readonly canRefresh: boolean;
}

// rainbow is reactive-only, so the timing fields are not stored. The session id
// and the tier are all a page load needs.
const toSession = (response: APISessionResponse): Session => {
    if (!validateSessionId(response.sessionId)) {
        throw new Error("Invalid session id in the flashlight auth response");
    }
    if (!isTier(response.tier)) {
        captureMessage("Unknown tier in the flashlight auth response", {
            level: "error",
            extra: { tier: response.tier },
        });
        return { sessionId: response.sessionId, tier: "anonymous" };
    }
    return { sessionId: response.sessionId, tier: response.tier };
};

export const requestChallenge = async (userId: string): Promise<Challenge> => {
    const { data } = await flashlightRequest<APIChallengeResponse>(
        "/v1/auth/anonymous/challenge",
        {
            init: { method: "POST", body: JSON.stringify({ userId }) },
            errorContext: "Failed to get an auth challenge",
            extra: { userId },
        },
    );
    return {
        challenge: data.challenge,
        algorithm: data.algorithm,
        difficulty: data.difficulty,
    };
};

interface LoginOptions {
    readonly userId: string;
    readonly challenge: string;
    readonly solution: string;
}

export const anonymousLogin = async ({
    userId,
    challenge,
    solution,
}: LoginOptions): Promise<Session> => {
    const { data } = await flashlightRequest<APISessionResponse>(
        "/v1/auth/anonymous/login",
        {
            init: {
                method: "POST",
                body: JSON.stringify({ userId, challenge, solution }),
            },
            errorContext: "Failed to log in anonymously",
            extra: { userId },
        },
    );
    return toSession(data);
};

export interface APIMicrosoftSessionResponse extends APISessionResponse {
    readonly uuid: string;
}

const toMicrosoftSession = (response: APIMicrosoftSessionResponse): Session =>
    withUUID(toSession(response), response.uuid);

/**
 * Exchange the result token from the Microsoft callback for a session.
 *
 * Throws a FlashlightResponseError with status 401 when the result expired or
 * the verifier is wrong. Not retried: the result is single-purpose.
 */
export const exchangeMicrosoftResult = async (
    result: string,
    verifier: string,
): Promise<Session> => {
    const { data } = await flashlightRequest<APIMicrosoftSessionResponse>(
        "/v1/auth/microsoft/exchange",
        {
            // include, so the browser keeps the fl_rm cookie flashlight sets.
            init: {
                method: "POST",
                credentials: "include",
                body: JSON.stringify({ result, verifier }),
            },
            errorContext: "Failed to exchange the Microsoft sign-in result",
            extra: {},
            expectedStatuses: [401],
        },
    );
    return toMicrosoftSession(data);
};

/**
 * Get a new microsoft session chain with the fl_rm cookie.
 *
 * Returns null on a 401 (no usable credential: sign in again). Throws on any
 * other error, and the caller must keep its session then.
 *
 * Staging and previews (*.rainbow-ctx.pages.dev) are cross-site to flashlight,
 * so the SameSite=Lax fl_rm cookie is never sent there and recover 401s once
 * the 24h session chain ends. Expected; moving staging to *.prismoverlay.com
 * would fix it and let flashlight's CORS allowlist drop pages.dev.
 */
export const recoverSession = async (): Promise<Session | null> => {
    try {
        const { data } = await flashlightRequest<APIMicrosoftSessionResponse>(
            "/v1/auth/recover",
            {
                // An empty body is a 400.
                init: { method: "POST", credentials: "include", body: "{}" },
                errorContext: "Failed to recover the session",
                extra: {},
                expectedStatuses: [401],
            },
        );
        return toMicrosoftSession(data);
    } catch (error: unknown) {
        if (error instanceof FlashlightResponseError && error.status === 401) {
            return null;
        }
        throw error;
    }
};

/**
 * Delete every credential for the signed-in identity.
 *
 * A 401 means there is nothing to sign out of, so it counts as done. Throws on
 * any other error, and the caller must keep its local state then.
 */
export const logout = async (): Promise<void> => {
    try {
        await flashlightRequest<undefined>("/v1/auth/logout", {
            init: { method: "POST", credentials: "include", body: "{}" },
            errorContext: "Failed to sign out",
            extra: {},
            expectedStatuses: [401],
        });
    } catch (error: unknown) {
        if (error instanceof FlashlightResponseError && error.status === 401) {
            return;
        }
        throw error;
    }
};

/**
 * Refresh a session.
 *
 * Returns the refreshed session with `session`'s uuid, `session` unchanged on a 429 (refreshed too
 * recently, or rate limited — the session is untouched and must be reused), or
 * null on a 401 (the session is finished; re-auth from scratch).
 */
export const refreshSession = async (session: Session): Promise<Session | null> => {
    try {
        const { data } = await flashlightRequest<APISessionResponse>(
            "/v1/auth/refresh",
            {
                init: { method: "POST" },
                errorContext: "Failed to refresh the session",
                extra: { tier: session.tier },
                bearer: session.sessionId,
                expectedStatuses: [401, 429],
            },
        );
        // Refresh does not return the uuid, so carry it forward.
        return withUUID(toSession(data), session.uuid);
    } catch (error: unknown) {
        if (error instanceof FlashlightResponseError) {
            if (error.status === 401) {
                return null;
            }
            if (error.status === 429) {
                return session;
            }
        }
        throw error;
    }
};
