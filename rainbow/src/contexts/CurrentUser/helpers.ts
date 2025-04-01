import { isUUID } from "#helpers/uuid.ts";

const localStorageKey = "currentUser";

const parseStoredUUID = (stored: string | null): string | null => {
    if (stored === null) {
        return null;
    }

    if (!isUUID(stored)) {
        return null;
    }

    return stored;
};

export const clearPersistedCurrentUser = (): void => {
    localStorage.removeItem(localStorageKey);
};

export const setPersistedCurrentUser = (uuid: string): void => {
    localStorage.setItem(localStorageKey, uuid);
};

export const getPersistedCurrentUser = (): string | null => {
    const stored = localStorage.getItem(localStorageKey);

    return parseStoredUUID(stored);
};
