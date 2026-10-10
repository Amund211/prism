import { captureException } from "@sentry/react";

import { getOrSetUserId } from "#helpers/userId.ts";

import {
    anonymousLogin,
    logout,
    recoverSession,
    refreshSession,
    requestChallenge,
} from "./api.ts";
import { solve } from "./solve.ts";
import { clearSession, readSession, writeSession } from "./storage.ts";
import type { Session } from "./storage.ts";

const AUTH_LOCK_NAME = "rainbow-auth";

// Web Locks are released when the holder's callback settles or its tab dies. A
// fetch that hangs is neither, and fetch has no default timeout, so without a
// bound one wedged login blocks every other tab indefinitely.
const AUTH_LOCK_TIMEOUT_MS = 10_000;

const withAuthLock = async <T>(run: () => Promise<T>): Promise<T> => {
    // Web Locks needs a secure context and Safari 15.4+. Without it the
    // module-level promise below still dedupes within this document, and the
    // worst case is one spare session.
    const locks: LockManager | undefined = navigator.locks;
    if (locks === undefined) {
        return run();
    }

    let started = false;
    const guarded = async () => {
        started = true;
        return run();
    };

    try {
        return await locks.request(
            AUTH_LOCK_NAME,
            // AbortSignal.timeout is Safari 16+, so the lock is bounded on a
            // best-effort basis rather than always.
            { signal: AbortSignal.timeout(AUTH_LOCK_TIMEOUT_MS) },
            guarded,
        );
    } catch (error: unknown) {
        // An AbortError means "never acquired the lock" only if the callback
        // never ran — a fetch aborted inside it throws the same name.
        if (started) {
            throw error;
        }
        // A spare session is strictly better than a tab that never loads.
        return run();
    }
};

// The anonymous handshake: challenge, solve, login. Keep this the only
// tier-specific function — locking, refresh, retry and storage stay tier-blind.
const acquireSession = async (): Promise<Session> => {
    // Read the user id once: flashlight binds the challenge to it and compares
    // it byte for byte at login.
    const userId = getOrSetUserId();

    const challenge = await requestChallenge(userId);
    const solution = await solve(challenge);

    return anonymousLogin({ userId, challenge: challenge.challenge, solution });
};

const commit = (session: Session): Session => {
    writeSession(session);
    return session;
};

const acquire = async (observed: Session | null): Promise<Session> =>
    withAuthLock(async () => {
        const stored = readSession();

        // Someone else already replaced the session we tried. Adopt theirs.
        // Comparing ids, not presence: a loser that only checks presence goes
        // on to refresh a token the winner already replaced.
        if (stored !== null && stored.sessionId !== observed?.sessionId) {
            return stored;
        }

        if (stored === null) {
            return commit(await acquireSession());
        }

        const refreshed = await refreshSession(stored);
        if (refreshed !== null) {
            return commit(refreshed);
        }

        if (stored.tier === "microsoft") {
            // Throws on a 429 or 5xx before anything is cleared: a transient
            // error must not sign the user out.
            const recovered = await recoverSession();
            if (recovered !== null) {
                return commit(recovered);
            }
        }

        // The session is finished by definition. Drop it now so a failing
        // login doesn't leave later requests paying for a refresh that cannot
        // succeed.
        clearSession();
        return commit(await acquireSession());
    });

let inFlight: Promise<Session> | null = null;

const setInFlight = async (run: () => Promise<Session>): Promise<Session> => {
    const promise = run();
    inFlight = promise;
    try {
        return await promise;
    } finally {
        if (inFlight === promise) {
            inFlight = null;
        }
    }
};

/**
 * Store a session from a sign-in, under the same lock as refresh and login.
 *
 * Resolves with `session`. Until then, ensureSession callers wait for it.
 */
export const adoptSession = async (session: Session): Promise<Session> => {
    // The lock alone is not enough: without Web Locks, or past its timeout, an
    // in-flight acquire would commit after this and overwrite the sign-in.
    const previous = inFlight;
    return setInFlight(async () => {
        await previous?.catch(() => null);
        // oxlint-disable-next-line typescript/require-await -- withAuthLock takes an async callback
        return withAuthLock(async () => commit(session));
    });
};

/**
 * Sign out every client of the signed-in identity, then continue anonymous.
 *
 * Throws if logout fails, and keeps the session then.
 */
export const signOutEverywhere = async (): Promise<void> => {
    await logout();
    // Through inFlight, like adoptSession: an acquire in flight would
    // otherwise store the microsoft session again after the clear.
    const previous = inFlight;
    try {
        await setInFlight(async () => {
            await previous?.catch(() => null);
            return withAuthLock(async () => {
                clearSession();
                return commit(await acquireSession());
            });
        });
    } catch (error: unknown) {
        // The sign-out is done. The next request logs in again.
        captureException(error, {
            extra: { message: "Failed to log in anonymously after sign-out" },
        });
    }
};

/**
 * Get a usable session, refreshing or logging in as needed.
 *
 * `observed` is the session the caller held when it saw a 401 (or the refresh
 * hint), or null if it held none.
 */
export const ensureSession = async (observed: Session | null): Promise<Session> =>
    inFlight ?? setInFlight(async () => acquire(observed));

/**
 * Acquire a session in the background, at app boot.
 *
 * Overlaps the login round-trip with the app starting up; single-flight makes
 * the first real query await this same promise.
 */
export const startSession = async (): Promise<void> => {
    try {
        await ensureSession(null);
    } catch (error: unknown) {
        captureException(error, {
            extra: { message: "Failed to acquire a session at boot" },
        });
    }
};
