import React, { useEffect, useMemo, useRef } from "react";
import { createPortal } from "react-dom";
import { toPng } from "html-to-image";

/**
 * Offscreen host:
 * - Must be in DOM (document.body) to compute layout/styles reliably
 * - Must NOT be display:none (often becomes 0x0 / blank)
 */
function useOffscreenHost() {
    const host = useMemo(() => document.createElement("div"), []);
    useEffect(() => {
        Object.assign(host.style, {
            position: "fixed",
            left: "-10000px",
            top: "0",
            width: "max-content",
            height: "max-content",
            opacity: "0",
            pointerEvents: "none",
            zIndex: "-1",
        });
        document.body.appendChild(host);
        return () => void document.body.removeChild(host);
    }, [host]);
    return host;
}

/** Wait for <img> in a subtree to finish loading/decoding */
async function waitForImages(root: HTMLElement) {
    const imgs = Array.from(root.querySelectorAll("img"));
    await Promise.all(
        imgs.map(async (img) => {
            if (img.complete && img.naturalWidth > 0) return;
            await new Promise<void>((resolve, reject) => {
                img.onload = () => {
                    resolve();
                };
                img.onerror = () => {
                    reject(new Error(`Image failed: ${img.src}`));
                };
            });
        }),
    );
    // img.decode() may not be available in all browsers
    await Promise.allSettled(
        imgs.map((img) => {
            const imgWithDecode = img as HTMLImageElement & {
                decode?: () => Promise<void>;
            };
            // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
            if (imgWithDecode.decode) {
                return imgWithDecode.decode();
            }
            return Promise.resolve();
        }),
    );
}

/** Wait for web fonts (helps avoid fallback font in export) */
async function waitForFonts() {
    // document.fonts may not be available in all browsers
    if ("fonts" in document) {
        await document.fonts.ready;
    }
}

function downloadDataUrl(dataUrl: string, filename: string) {
    const a = document.createElement("a");
    a.href = dataUrl;
    a.download = filename;
    a.click();
}

/** Wait for React commit and layout to settle before capturing */
async function waitForLayoutSettlement() {
    await new Promise((resolve) => {
        requestAnimationFrame(() => {
            resolve(null);
        });
    });
    await new Promise((resolve) => {
        requestAnimationFrame(() => {
            resolve(null);
        });
    });
}

interface ExportImageMountProps {
    children: React.ReactNode;
    /** Optional: expose a ref callback so caller can trigger export */
    onReady?: (api: { download: () => Promise<void> }) => void;
    /** Optional: callback before a capture is done */
    onCapture?: (node: HTMLDivElement) => void;
    filename?: string;
}

/**
 * Mount this component once somewhere near the root of your app,
 * then call the download function from the onReady callback.
 */
export function ExportImageMount({
    children,
    onReady,
    onCapture,
    filename,
}: ExportImageMountProps) {
    const host = useOffscreenHost();
    const captureRef = useRef<HTMLDivElement | null>(null);

    const download = React.useCallback(async () => {
        const node = captureRef.current;
        if (!node) return;

        onCapture?.(node);
        await waitForLayoutSettlement();
        await waitForFonts();
        await waitForImages(node);

        const dataUrl = await toPng(node, {
            cacheBust: true,
            backgroundColor: "#ffffff",
            skipFonts: true,
            pixelRatio: 1,
        });

        downloadDataUrl(dataUrl, filename ?? "export.png");
    }, [filename, onCapture]);

    useEffect(() => {
        if (onReady) {
            onReady({ download });
        }
    }, [onReady, download]);

    return createPortal(<div ref={captureRef}>{children}</div>, host);
}
