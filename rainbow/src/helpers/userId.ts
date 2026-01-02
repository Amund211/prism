import { captureMessage } from "@sentry/react";

const USER_ID_LOCAL_STORAGE_KEY = "rainbow_user_id";

const RAINBOW_USER_ID_PREFIX = "rnb_";

export const LOCAL_DEVELOPMENT_USER_ID = `${RAINBOW_USER_ID_PREFIX}local_development`;

export const validateUserId = (userId: string | null): userId is string => {
    if (userId === null) {
        return false;
    }

    if (!userId.startsWith(RAINBOW_USER_ID_PREFIX)) {
        return false;
    }

    return true;
};

const getUserId = (): string | null => {
    const rawUserId = localStorage.getItem(USER_ID_LOCAL_STORAGE_KEY);
    if (!validateUserId(rawUserId)) {
        return null;
    }
    return rawUserId;
};

function setUserId(userId: string): string {
    localStorage.setItem(USER_ID_LOCAL_STORAGE_KEY, userId);
    return userId;
}

const randomHexString = (length: number): string => {
    return new Array(length)
        .fill(null)
        .map(() => {
            const randomHex = Math.floor(Math.random() * 16).toString(16);
            return randomHex;
        })
        .join("");
};

const fallbackRandomId = (): string => {
    return new Array(4)
        .fill(null)
        .map(() => randomHexString(12))
        .join("-");
};

const randomId = (): string => {
    if (
        typeof crypto === "undefined" ||
        typeof crypto.randomUUID !== "function"
    ) {
        // Fallback for environments without crypto.randomUUID
        captureMessage(
            "crypto.randomUUID is not available, using fallback random ID generation.",
            {
                level: "info",
                tags: {
                    missingCrypto: String(typeof crypto === "undefined"),
                    missingRandomUUID: String(
                        typeof crypto.randomUUID !== "function",
                    ),
                },
            },
        );

        return fallbackRandomId();
    }

    return crypto.randomUUID();
};

export const newUserId = (): string => {
    const uuid = randomId();
    return `${RAINBOW_USER_ID_PREFIX}${uuid}`;
};

export function getOrSetUserId(): string {
    // In local development, return a hardcoded user ID
    if (import.meta.env.DEV) {
        return LOCAL_DEVELOPMENT_USER_ID;
    }

    return getUserId() ?? setUserId(newUserId());
}
