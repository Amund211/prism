import { captureException } from "@sentry/react";
import { afterEach, describe, expect, test, vi } from "vitest";

import {
    clearSession,
    getSessionSnapshot,
    readSession,
    writeSession,
} from "./storage.ts";
import type { Session } from "./storage.ts";

vi.mock(import("@sentry/react"), () => ({
    captureException: vi.fn<typeof captureException>(),
}));

const SESSION_LOCAL_STORAGE_KEY = "rainbow_auth_session";

// The shape the stateless cutover mints: flsess_<payload>.<signature>. A
// released client that discards it turns every page load into a fresh login.
const STATELESS_SESSION_ID = "flsess_eyJ0eXAiOiJmbHNlc3MvMSJ9.c2lnbmF0dXJl";

// The row-backed shape, still stored in browsers when the cutover lands.
const ROW_BACKED_SESSION_ID = "flsess_0f1e2d3c4b5a6978";

const TEST_UUID = "0123abcd-4567-89ef-0123-456789abcdef";

type StorageMethod = "getItem" | "setItem" | "removeItem";

const stubStorage = (throwOn: readonly StorageMethod[] = []): Map<string, string> => {
    const store = new Map<string, string>();
    const guard = (method: StorageMethod): void => {
        if (throwOn.includes(method)) {
            throw new Error(`localStorage.${method} is unavailable`);
        }
    };

    vi.stubGlobal("localStorage", {
        getItem: (key: string): string | null => {
            guard("getItem");
            return store.get(key) ?? null;
        },
        setItem: (key: string, value: string): void => {
            guard("setItem");
            store.set(key, value);
        },
        removeItem: (key: string): void => {
            guard("removeItem");
            store.delete(key);
        },
    });

    return store;
};

const stored = (value: unknown): string => JSON.stringify(value);

afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
});

describe(readSession, () => {
    test("returns null when nothing is stored", () => {
        stubStorage();

        expect(readSession()).toBeNull();
    });

    test("accepts a dotted, stateless handle", () => {
        const store = stubStorage();
        store.set(
            SESSION_LOCAL_STORAGE_KEY,
            stored({ v: 1, sessionId: STATELESS_SESSION_ID, tier: "anonymous" }),
        );

        expect(readSession()).toStrictEqual({
            sessionId: STATELESS_SESSION_ID,
            tier: "anonymous",
        });
    });

    test("accepts a row-backed handle from the old format", () => {
        const store = stubStorage();
        store.set(
            SESSION_LOCAL_STORAGE_KEY,
            stored({ v: 1, sessionId: ROW_BACKED_SESSION_ID, tier: "anonymous" }),
        );

        expect(readSession()).toStrictEqual({
            sessionId: ROW_BACKED_SESSION_ID,
            tier: "anonymous",
        });
    });

    // Every one of these must leave "no session" *and* an empty key: a value
    // that fails on every subsequent load follows that browser around forever,
    // and is the one failure neither rollback lever undoes.
    test.for([
        ["garbage", "not json at all"],
        ["a JSON null", stored(null)],
        ["a JSON array", stored([])],
        ["a bare string", stored(STATELESS_SESSION_ID)],
        [
            "a missing envelope version",
            stored({ sessionId: STATELESS_SESSION_ID, tier: "anonymous" }),
        ],
        [
            "a future envelope version",
            stored({ v: 2, sessionId: STATELESS_SESSION_ID, tier: "anonymous" }),
        ],
        ["a non-string session id", stored({ v: 1, sessionId: 42, tier: "anonymous" })],
        ["a null session id", stored({ v: 1, sessionId: null, tier: "anonymous" })],
        [
            "a session id without the prefix",
            stored({ v: 1, sessionId: "nope", tier: "anonymous" }),
        ],
        ["a missing session id", stored({ v: 1, tier: "anonymous" })],
        [
            "an unknown tier",
            stored({ v: 1, sessionId: STATELESS_SESSION_ID, tier: "premium" }),
        ],
        ["a missing tier", stored({ v: 1, sessionId: STATELESS_SESSION_ID })],
    ] as const)("clears the key on %s", ([, raw]) => {
        const store = stubStorage();
        store.set(SESSION_LOCAL_STORAGE_KEY, raw);

        expect(readSession()).toBeNull();
        expect(store.has(SESSION_LOCAL_STORAGE_KEY)).toBe(false);
        expect(readSession()).toBeNull();
    });

    // v1 without a uuid is what every browser stores today, and what a rollback
    // leaves behind.
    test("accepts a microsoft session without a uuid", () => {
        const store = stubStorage();
        store.set(
            SESSION_LOCAL_STORAGE_KEY,
            stored({ v: 1, sessionId: STATELESS_SESSION_ID, tier: "microsoft" }),
        );

        expect(readSession()).toStrictEqual({
            sessionId: STATELESS_SESSION_ID,
            tier: "microsoft",
        });
    });

    // A bad uuid costs the "Signed in as" name, not the session.
    test.for([
        ["a non-string uuid", 42],
        ["an undashed uuid", TEST_UUID.replaceAll("-", "")],
        ["an uppercase uuid", TEST_UUID.toUpperCase()],
        ["a non-uuid string", "steve"],
    ] as const)("drops %s but keeps the session", ([, uuid]) => {
        const store = stubStorage();
        store.set(
            SESSION_LOCAL_STORAGE_KEY,
            stored({ v: 1, sessionId: STATELESS_SESSION_ID, tier: "microsoft", uuid }),
        );

        expect(readSession()).toStrictEqual({
            sessionId: STATELESS_SESSION_ID,
            tier: "microsoft",
        });
    });

    test("drops a uuid on an anonymous session", () => {
        const store = stubStorage();
        store.set(
            SESSION_LOCAL_STORAGE_KEY,
            stored({
                v: 1,
                sessionId: STATELESS_SESSION_ID,
                tier: "anonymous",
                uuid: TEST_UUID,
            }),
        );

        expect(readSession()).toStrictEqual({
            sessionId: STATELESS_SESSION_ID,
            tier: "anonymous",
        });
    });

    test("returns null when localStorage throws on read", () => {
        stubStorage(["getItem"]);

        expect(readSession()).toBeNull();
    });

    test("does not throw when the rejected value cannot be cleared either", () => {
        const store = stubStorage(["removeItem"]);
        store.set(SESSION_LOCAL_STORAGE_KEY, "not json at all");

        expect(readSession()).toBeNull();
    });

    test("recovers a browser holding a rejected value", () => {
        const store = stubStorage();
        store.set(SESSION_LOCAL_STORAGE_KEY, "not json at all");
        const session: Session = { sessionId: STATELESS_SESSION_ID, tier: "anonymous" };

        expect(readSession()).toBeNull();
        writeSession(session);

        expect(readSession()).toStrictEqual(session);
    });
});

describe(writeSession, () => {
    test("round-trips a session", () => {
        stubStorage();
        const session: Session = { sessionId: STATELESS_SESSION_ID, tier: "microsoft" };

        writeSession(session);

        expect(readSession()).toStrictEqual(session);
    });

    test("round-trips a microsoft session with a uuid", () => {
        stubStorage();
        const session: Session = {
            sessionId: STATELESS_SESSION_ID,
            tier: "microsoft",
            uuid: TEST_UUID,
        };

        writeSession(session);

        expect(readSession()).toStrictEqual(session);
    });

    test("does not throw when localStorage refuses the write", () => {
        stubStorage(["setItem"]);

        expect(() => {
            writeSession({ sessionId: STATELESS_SESSION_ID, tier: "anonymous" });
        }).not.toThrow();
    });
});

describe(getSessionSnapshot, () => {
    test("returns the same object until the stored value changes", () => {
        stubStorage();
        writeSession({ sessionId: STATELESS_SESSION_ID, tier: "anonymous" });

        const first = getSessionSnapshot();
        expect(getSessionSnapshot()).toBe(first);

        writeSession({ sessionId: ROW_BACKED_SESSION_ID, tier: "anonymous" });
        expect(getSessionSnapshot()).not.toBe(first);
    });

    // It runs on every render, so a report here floods Sentry.
    test("does not report when localStorage throws", () => {
        stubStorage(["getItem"]);

        expect(getSessionSnapshot()).toBeNull();
        expect(captureException).not.toHaveBeenCalled();
    });
});

describe(clearSession, () => {
    test("removes the stored session", () => {
        const store = stubStorage();
        writeSession({ sessionId: STATELESS_SESSION_ID, tier: "anonymous" });

        clearSession();

        expect(store.has(SESSION_LOCAL_STORAGE_KEY)).toBe(false);
        expect(readSession()).toBeNull();
    });

    test("does not throw when localStorage throws", () => {
        stubStorage(["removeItem"]);

        expect(() => {
            clearSession();
        }).not.toThrow();
    });
});
