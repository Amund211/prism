import { captureException } from "@sentry/react";

import { isNormalizedUUID } from "#helpers/uuid.ts";

const SESSION_LOCAL_STORAGE_KEY = "rainbow_auth_session";

const SESSION_ID_PREFIX = "flsess_";

const TIERS = ["anonymous", "microsoft"] as const;
export type Tier = (typeof TIERS)[number];

export interface Session {
    readonly sessionId: string;
    readonly tier: Tier;
    // The signed-in player, dashed lowercase. Only exchange and recover return
    // it, so a refresh carries it forward. Optional even on a microsoft session.
    readonly uuid?: string;
}

// Only the session id, the tier and the uuid are persisted. A monotonic
// deadline does not survive a page load (performance.now() is per-document),
// and persisting an absolute one would mean trusting the local wall clock. The
// version field makes a future format change a discard rather than a parse
// crash. The uuid is still v1: the old parser ignores it, so a rollback only
// loses the name.
interface StoredSession {
    readonly v: 1;
    readonly sessionId: string;
    readonly tier: Tier;
    readonly uuid?: string;
}

export const isTier = (value: unknown): value is Tier =>
    typeof value === "string" && (TIERS as readonly string[]).includes(value);

export const validateSessionId = (sessionId: unknown): sessionId is string =>
    typeof sessionId === "string" && sessionId.startsWith(SESSION_ID_PREFIX);

/**
 * Attach `uuid` to a microsoft session. Any other tier, or a bad uuid, gets
 * none: it costs the name, never the session.
 */
export const withUUID = (session: Session, uuid: unknown): Session => {
    const { sessionId, tier } = session;
    return tier === "microsoft" && typeof uuid === "string" && isNormalizedUUID(uuid)
        ? { sessionId, tier, uuid }
        : { sessionId, tier };
};

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

    return withUUID(
        { sessionId: parsed.sessionId, tier: parsed.tier },
        "uuid" in parsed ? parsed.uuid : undefined,
    );
};

// Same-tab change notifications. The `storage` event covers other tabs.
const sessionEvents = new EventTarget();
const SESSION_CHANGE_EVENT = "change";

const notifyChange = (): void => {
    sessionEvents.dispatchEvent(new Event(SESSION_CHANGE_EVENT));
};

/**
 * Subscribe to changes of the stored session, in this tab and in others.
 *
 * Returns the unsubscribe function.
 */
export const subscribeSession = (onChange: () => void): (() => void) => {
    const storageListener = (event: StorageEvent) => {
        // `key` is null on clear.
        if (event.key === SESSION_LOCAL_STORAGE_KEY || event.key === null) {
            onChange();
        }
    };
    sessionEvents.addEventListener(SESSION_CHANGE_EVENT, onChange);
    globalThis.addEventListener("storage", storageListener);
    return () => {
        sessionEvents.removeEventListener(SESSION_CHANGE_EVENT, onChange);
        globalThis.removeEventListener("storage", storageListener);
    };
};

export const clearSession = (): void => {
    try {
        localStorage.removeItem(SESSION_LOCAL_STORAGE_KEY);
    } catch (error: unknown) {
        captureException(error, {
            extra: { message: "Failed to clear the stored auth session" },
        });
    }
    notifyChange();
};

const readRaw = (): string | null => {
    try {
        return localStorage.getItem(SESSION_LOCAL_STORAGE_KEY);
    } catch (error: unknown) {
        captureException(error, {
            extra: { message: "Failed to read the stored auth session" },
        });
        return null;
    }
};

export const readSession = (): Session | null => {
    const raw = readRaw();
    if (raw === null) {
        return null;
    }

    const session = parseSession(raw);
    if (session === null) {
        clearSession();
    }
    return session;
};

let snapshot: { readonly raw: string | null; readonly session: Session | null } = {
    raw: null,
    session: null,
};

/**
 * The stored session, as the same object until the stored value changes.
 *
 * For useSyncExternalStore, which needs a stable snapshot.
 */
export const getSessionSnapshot = (): Session | null => {
    // Not readRaw: this runs on every render, and readRaw reports each failure.
    let raw: string | null = null;
    try {
        raw = localStorage.getItem(SESSION_LOCAL_STORAGE_KEY);
    } catch {
        // readSession reports it.
    }
    if (raw !== snapshot.raw) {
        snapshot = { raw, session: raw === null ? null : parseSession(raw) };
    }
    return snapshot.session;
};

export const writeSession = (session: Session): void => {
    const stored: StoredSession = {
        v: 1,
        sessionId: session.sessionId,
        tier: session.tier,
        ...(session.uuid === undefined ? {} : { uuid: session.uuid }),
    };
    try {
        localStorage.setItem(SESSION_LOCAL_STORAGE_KEY, JSON.stringify(stored));
    } catch (error: unknown) {
        captureException(error, {
            extra: { message: "Failed to store the auth session" },
        });
    }
    notifyChange();
};
