import { isNormalizedUUID } from "#helpers/uuid.ts";

export const localStorageKey = "currentUser";

export const parseStoredUUID = (stored: string | null): string | null => {
    if (stored === null) {
        return null;
    }

    if (!isNormalizedUUID(stored)) {
        return null;
    }

    return stored;
};
