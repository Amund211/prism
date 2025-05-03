export const normalizeUUID = (uuid: string) => {
    const cleaned = uuid.replace(/[^\da-fA-F]/g, "").toLowerCase();

    if (cleaned.length !== 32) {
        throw new Error(`Invalid UUID: ${uuid}`);
    }

    return `${cleaned.slice(0, 8)}-${cleaned.slice(8, 12)}-${cleaned.slice(
        12,
        16,
    )}-${cleaned.slice(16, 20)}-${cleaned.slice(20)}`;
};

export const isUUID = (value: string) => {
    try {
        normalizeUUID(value);
    } catch {
        return false;
    }
    return true;
};

export const isNormalizedUUID = (value: string) => {
    let normalized: string | null = null;
    try {
        normalized = normalizeUUID(value);
    } catch {
        return false;
    }
    return normalized === value;
};
