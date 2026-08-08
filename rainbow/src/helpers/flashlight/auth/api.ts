import { captureMessage } from "@sentry/react";

import {
    FlashlightResponseError,
    flashlightRequest,
} from "#helpers/flashlight/request.ts";

import type { Challenge } from "./proofOfWork.ts";
import { isTier, validateSessionId } from "./storage.ts";
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

/**
 * Refresh a session.
 *
 * Returns the refreshed session, `session` unchanged on a 429 (refreshed too
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
        return toSession(data);
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
