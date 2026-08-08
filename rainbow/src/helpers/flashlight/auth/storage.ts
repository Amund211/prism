import { captureException } from "@sentry/react";

const SESSION_LOCAL_STORAGE_KEY = "rainbow_auth_session";

const SESSION_ID_PREFIX = "flsess_";

const TIERS = ["anonymous", "microsoft"] as const;
export type Tier = (typeof TIERS)[number];

export interface Session {
    readonly sessionId: string;
    readonly tier: Tier;
}

// Only the session id and the tier are persisted. A monotonic deadline does not
// survive a page load (performance.now() is per-document), and persisting an
// absolute one would mean trusting the local wall clock. The version field
// makes a future format change a discard rather than a parse crash.
interface StoredSession {
    readonly v: 1;
    readonly sessionId: string;
    readonly tier: Tier;
}

export const isTier = (value: unknown): value is Tier =>
    typeof value === "string" && (TIERS as readonly string[]).includes(value);

export const validateSessionId = (sessionId: unknown): sessionId is string =>
    typeof sessionId === "string" && sessionId.startsWith(SESSION_ID_PREFIX);

const parseSession = (raw: string): Session | null => {
    let parsed: unknown;
    try {
        parsed = JSON.parse(raw);
    } catch {
        return null;
    }

    if (typeof parsed !== "object" || parsed === null) {
        return null;
    }
    if (!("v" in parsed) || parsed.v !== 1) {
        return null;
    }
    if (!("sessionId" in parsed) || !validateSessionId(parsed.sessionId)) {
        return null;
    }
    if (!("tier" in parsed) || !isTier(parsed.tier)) {
        return null;
    }

    return { sessionId: parsed.sessionId, tier: parsed.tier };
};

export const clearSession = (): void => {
    try {
        localStorage.removeItem(SESSION_LOCAL_STORAGE_KEY);
    } catch (error: unknown) {
        captureException(error, {
            extra: { message: "Failed to clear the stored auth session" },
        });
    }
};

export const readSession = (): Session | null => {
    let raw: string | null = null;
    try {
        raw = localStorage.getItem(SESSION_LOCAL_STORAGE_KEY);
    } catch (error: unknown) {
        captureException(error, {
            extra: { message: "Failed to read the stored auth session" },
        });
        return null;
    }
    if (raw === null) {
        return null;
    }

    const session = parseSession(raw);
    if (session === null) {
        clearSession();
    }
    return session;
};

export const writeSession = (session: Session): void => {
    const stored: StoredSession = {
        v: 1,
        sessionId: session.sessionId,
        tier: session.tier,
    };
    try {
        localStorage.setItem(SESSION_LOCAL_STORAGE_KEY, JSON.stringify(stored));
    } catch (error: unknown) {
        captureException(error, {
            extra: { message: "Failed to store the auth session" },
        });
    }
};
