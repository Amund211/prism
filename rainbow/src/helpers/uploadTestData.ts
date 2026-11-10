import { PNG_SIGNATURE } from "./upload.ts";

/**
 * A PNG signature and IHDR chunk, then filler. Only the header is read in the
 * browser, so the CRC and the rest are left as zeros. For tests only.
 */
export const makePNG = (
    width: number,
    height: number,
    colorType: number,
    filler = 16,
): Uint8Array<ArrayBuffer> => {
    const bytes = new Uint8Array(33 + filler);
    const view = new DataView(bytes.buffer);
    bytes.set(PNG_SIGNATURE, 0);
    view.setUint32(8, 13);
    bytes.set(new TextEncoder().encode("IHDR"), 12);
    view.setUint32(16, width);
    view.setUint32(20, height);
    bytes[24] = 8;
    bytes[25] = colorType;
    return bytes;
};
