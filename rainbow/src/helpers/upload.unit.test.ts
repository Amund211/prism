import { describe, expect, test, vi } from "vitest";

import { checkScreenshot, MAX_FILE_BYTES, readPNGInfo } from "./upload.ts";
import { makePNG } from "./uploadTestData.ts";

describe(readPNGInfo, () => {
    test("reads the size and colour type", async () => {
        await expect(
            readPNGInfo(new Blob([makePNG(2560, 1440, 6)])),
        ).resolves.toStrictEqual({ width: 2560, height: 1440, colorType: "rgba" });
        await expect(
            readPNGInfo(new Blob([makePNG(1920, 1080, 2)])),
        ).resolves.toStrictEqual({ width: 1920, height: 1080, colorType: "rgb" });
    });

    test("returns null for other files", async () => {
        await expect(
            readPNGInfo(new Blob(["GIF89a not a png at all"])),
        ).resolves.toBeNull();
        await expect(readPNGInfo(new Blob([]))).resolves.toBeNull();
        await expect(
            readPNGInfo(new Blob([makePNG(10, 10, 2).slice(0, 20)])),
        ).resolves.toBeNull();
    });

    test("reports other colour types", async () => {
        await expect(
            readPNGInfo(new Blob([makePNG(10, 10, 3)])),
        ).resolves.toStrictEqual({
            width: 10,
            height: 10,
            colorType: "other",
        });
    });
});

describe(checkScreenshot, () => {
    const file = (data: string | Uint8Array<ArrayBuffer>, name = "a.png") =>
        new File([data], name);

    test("accepts an original screenshot", async () => {
        await expect(
            checkScreenshot(file(makePNG(1920, 1080, 6))),
        ).resolves.toStrictEqual({
            ok: true,
            warning: null,
        });
    });

    test("rejects a file that is not a PNG", async () => {
        await expect(
            checkScreenshot(file("not a png at all, really", "a.jpg")),
        ).resolves.toStrictEqual({
            ok: false,
            reason: "Not a PNG file",
        });
    });

    test("rejects a converted PNG", async () => {
        await expect(
            checkScreenshot(file(makePNG(1920, 1080, 3))),
        ).resolves.toStrictEqual({
            ok: false,
            reason: "Not an original screenshot (the image was converted)",
        });
    });

    test("rejects a file that is too large", async () => {
        const big = new Uint8Array(MAX_FILE_BYTES + 1);
        big.set(makePNG(1920, 1080, 6));
        await expect(checkScreenshot(file(big))).resolves.toStrictEqual({
            ok: false,
            reason: "Larger than 10 MB",
        });
    });

    test("rejects a file that cannot be read", async () => {
        const unreadable = file(makePNG(1920, 1080, 6));
        const blob = new Blob();
        vi.spyOn(blob, "arrayBuffer").mockRejectedValue(
            new DOMException("gone", "NotReadableError"),
        );
        vi.spyOn(unreadable, "slice").mockReturnValue(blob);
        await expect(checkScreenshot(unreadable)).resolves.toStrictEqual({
            ok: false,
            reason: "Could not read the file",
        });
    });

    test("warns about a small image", async () => {
        await expect(
            checkScreenshot(file(makePNG(800, 400, 6))),
        ).resolves.toStrictEqual({
            ok: true,
            warning: "Small image (800×400). Was it cropped or scaled?",
        });
    });
});
