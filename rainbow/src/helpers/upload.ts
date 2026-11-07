// Limits that match flashlight's tabcap upload kind.
export const MAX_FILE_BYTES = 10 * 1024 * 1024;
export const MAX_FILES = 30;
export const MAX_TOTAL_BYTES = 200 * 1024 * 1024;

// Minecraft's default window size. Smaller images were likely cropped or scaled.
const MIN_WIDTH = 854;
const MIN_HEIGHT = 480;

// "\x89PNG\r\n\x1a\n"
export const PNG_SIGNATURE = [137, 80, 78, 71, 13, 10, 26, 10] as const;
const PNG_HEADER_BYTES = 33;

export interface PNGInfo {
    readonly width: number;
    readonly height: number;
    // Minecraft saves rgb or rgba. Anything else was converted afterwards.
    readonly colorType: "rgb" | "rgba" | "other";
}

const COLOR_TYPES: Readonly<Partial<Record<number, PNGInfo["colorType"]>>> = {
    2: "rgb",
    6: "rgba",
};

/** Read the size and colour type from a PNG header, or null if not a PNG. */
export const readPNGInfo = async (file: Readonly<Blob>): Promise<PNGInfo | null> => {
    const bytes = new Uint8Array(await file.slice(0, PNG_HEADER_BYTES).arrayBuffer());
    if (bytes.length < PNG_HEADER_BYTES) {
        return null;
    }
    if (PNG_SIGNATURE.some((byte, index) => bytes[index] !== byte)) {
        return null;
    }
    const view = new DataView(bytes.buffer);
    if (String.fromCodePoint(...bytes.subarray(12, 16)) !== "IHDR") {
        return null;
    }
    return {
        width: view.getUint32(16),
        height: view.getUint32(20),
        colorType: COLOR_TYPES[view.getUint8(25)] ?? "other",
    };
};

export type ScreenshotCheck =
    | { readonly ok: true; readonly warning: string | null }
    | { readonly ok: false; readonly reason: string };

/** A quick check before upload. The server checks again. */
export const checkScreenshot = async (
    file: Readonly<File>,
): Promise<ScreenshotCheck> => {
    if (file.size > MAX_FILE_BYTES) {
        return { ok: false, reason: "Larger than 10 MB" };
    }
    let info: PNGInfo | null;
    try {
        info = await readPNGInfo(file);
    } catch {
        // For example a folder, or a file deleted after it was chosen.
        return { ok: false, reason: "Could not read the file" };
    }
    if (info === null) {
        return { ok: false, reason: "Not a PNG file" };
    }
    if (info.colorType === "other") {
        return {
            ok: false,
            reason: "Not an original screenshot (the image was converted)",
        };
    }
    if (info.width < MIN_WIDTH || info.height < MIN_HEIGHT) {
        return {
            ok: true,
            warning: `Small image (${info.width.toString()}×${info.height.toString()}). Was it cropped or scaled?`,
        };
    }
    return { ok: true, warning: null };
};
