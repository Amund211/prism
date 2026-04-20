import React from "react";

declare global {
    interface WindowEventMap {
        // Assert that we will only publish events of the given type with this
        // event name so we're allowed to assign a handler with a typed event parameter.
        [EVENT_NAME]: CustomEvent<UseLocalStorageWriteEventPayload>;
    }
}

const EVENT_NAME = "useLocalStorageWrite";

interface UseLocalStorageWriteEventPayload {
    key: string;
    value: string | null;
}

const makeSubscribe = (key: string) => {
    return (onStoreChange: () => void) => {
        const customEventListener = (
            e: CustomEvent<UseLocalStorageWriteEventPayload>,
        ) => {
            if (e.detail.key !== key) return;

            onStoreChange();
        };

        const storageListener = (e: StorageEvent) => {
            // `key` is `null` on clear -> process it
            // https://developer.mozilla.org/en-US/docs/Web/API/Window/storage_event#event_properties
            if (e.key !== key && e.key !== null) return;

            onStoreChange();
        };

        // Listen to our custom event that we dispatch on write to localstorage to get
        // immediate updates in the same tab.
        // Listen to the storage event to get updates from other tabs.
        window.addEventListener(EVENT_NAME, customEventListener);
        window.addEventListener("storage", storageListener);

        return () => {
            window.removeEventListener(EVENT_NAME, customEventListener);
            window.removeEventListener("storage", storageListener);
        };
    };
};

const makeGetSnapshot = (key: string) => {
    return () => {
        return localStorage.getItem(key);
    };
};

/**
 * Create a write function for a given localStorage key, which updates any
 * useLocalStorage hooks subscribed to that key.
 */
export const makeLocalStorageWrite = (key: string) => {
    return (value: string | null) => {
        if (value === null) {
            localStorage.removeItem(key);
        } else {
            localStorage.setItem(key, value);
        }

        window.dispatchEvent(
            new CustomEvent<UseLocalStorageWriteEventPayload>(EVENT_NAME, {
                detail: { key, value },
            }),
        );
    };
};

export const useLocalStorage = (
    key: string,
): [string | null, (value: string | null) => void] => {
    const subscribe = React.useMemo(() => makeSubscribe(key), [key]);
    const getSnapshot = React.useMemo(() => makeGetSnapshot(key), [key]);
    const write = React.useMemo(() => makeLocalStorageWrite(key), [key]);

    return [React.useSyncExternalStore(subscribe, getSnapshot), write];
};
