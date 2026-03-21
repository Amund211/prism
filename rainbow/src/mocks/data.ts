import { isNormalizedUUID } from "#helpers/uuid.ts";

interface User {
    username: string;
    uuid: string;
}

export const USERS = {
    player1: {
        username: "PlayerOne",
        uuid: "01234567-89ab-cdef-0123-456789abcdef",
    },
    player2: {
        username: "PlayerTwo",
        uuid: "abcdef01-2345-6789-abcd-ef0123456789",
    },
} as const satisfies Record<string, User>;

const seenUUIDs = new Set<string>();
const seenUsernames = new Set<string>();
for (const { uuid, username } of Object.values(USERS)) {
    if (!isNormalizedUUID(uuid)) {
        throw new Error(`Invalid UUID for user ${uuid}`);
    }
    if (seenUUIDs.has(uuid)) {
        throw new Error(`Duplicate UUID found: ${uuid}`);
    }
    seenUUIDs.add(uuid);

    if (seenUsernames.has(username)) {
        throw new Error(`Duplicate username found: ${username}`);
    }
    seenUsernames.add(username);
}

export const findUserByUUID = (uuid: string): User | null => {
    for (const user of Object.values(USERS)) {
        if (user.uuid === uuid) {
            return user;
        }
    }
    return null;
};
