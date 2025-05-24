const USER_ID_LOCAL_STORAGE_KEY = "rainbow_user_id";

const RAINBOW_USER_ID_PREFIX = "rnb_";

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

export const newUserId = (): string => {
    const uuid = crypto.randomUUID();
    return `${RAINBOW_USER_ID_PREFIX}${uuid}`;
};

export function getOrSetUserId(): string {
    return getUserId() ?? setUserId(newUserId());
}
