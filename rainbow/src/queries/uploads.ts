import { captureMessage } from "@sentry/react";

import { flashlightFetch } from "#helpers/flashlight/fetch.ts";
import { FlashlightResponseError } from "#helpers/flashlight/request.ts";

// The version of the consent text on the upload page. Change it when the
// text changes, so each upload records what the user agreed to.
const UPLOAD_CONSENT_VERSION = "2026-11-07";

// Files sent to the bucket at the same time.
const PARALLEL_POSTS = 3;

export type UploadFields = Readonly<Record<string, string>>;

interface PostTarget {
    readonly url: string;
    readonly fields: Readonly<Record<string, string>>;
}

interface APIStartResponse {
    readonly uploadId: string;
    readonly files: readonly PostTarget[];
}

interface APICompleteResponse {
    readonly uploadId: string;
}

/** The upload was rejected. The message is safe to show to the user. */
export class UploadRejectedError extends Error {
    public constructor(message: string) {
        super(message);
        this.name = "UploadRejectedError";
    }
}

const REJECTED_STATUSES = [400, 404, 409, 413, 429] as const;

const causeFromBody = (body: string): string | null => {
    try {
        const parsed = JSON.parse(body) as { readonly cause?: unknown };
        return typeof parsed.cause === "string" ? parsed.cause : null;
    } catch {
        return null;
    }
};

const toRejected = (error: unknown): unknown => {
    if (
        !(error instanceof FlashlightResponseError) ||
        !(REJECTED_STATUSES as readonly number[]).includes(error.status)
    ) {
        return error;
    }
    if (error.status === 429) {
        return new UploadRejectedError(
            "Too many uploads. Wait a few minutes and try again.",
        );
    }
    return new UploadRejectedError(
        causeFromBody(error.body) ?? "The upload was rejected",
    );
};

// The signed policy fixes the name, type and size; "file" must come last.
const postFile = async (target: PostTarget, file: Readonly<File>): Promise<void> => {
    const body = new FormData();
    for (const [name, value] of Object.entries(target.fields)) {
        body.append(name, value);
    }
    body.append("file", file);
    const response = await fetch(target.url, { method: "POST", body });
    if (!response.ok) {
        throw new UploadRejectedError(
            `${file.name} was not accepted. Remove it or try again.`,
        );
    }
};

/**
 * Upload files with their fields: flashlight signs one POST per file, the
 * files go straight to storage, and flashlight then checks them.
 * Returns the upload ID.
 */
export const submitUpload = async ({
    kind,
    fields,
    files,
    onFileDone,
}: {
    readonly kind: string;
    readonly fields: UploadFields;
    readonly files: readonly File[];
    readonly onFileDone: (index: number) => void;
}): Promise<string> => {
    try {
        const started = await flashlightFetch<APIStartResponse>(
            `/v1/uploads/${encodeURIComponent(kind)}`,
            {
                init: {
                    method: "POST",
                    body: JSON.stringify({
                        consentVersion: UPLOAD_CONSENT_VERSION,
                        fields,
                        files: files.map((file) => ({
                            name: file.name,
                            bytes: file.size,
                        })),
                    }),
                },
                errorContext: "Failed to start upload",
                extra: { kind, fileCount: files.length },
                expectedStatuses: REJECTED_STATUSES,
            },
        );

        if (started.files.length !== files.length) {
            captureMessage("Failed to start upload: wrong number of targets", {
                level: "error",
                extra: { kind, fileCount: files.length, targets: started.files.length },
            });
            throw new Error("Wrong number of upload targets");
        }

        let next = 0;
        const worker = async (): Promise<void> => {
            while (next < files.length) {
                const index = next;
                next += 1;
                // oxlint-disable-next-line no-await-in-loop
                await postFile(started.files[index], files[index]);
                onFileDone(index);
            }
        };
        await Promise.all(
            Array.from({ length: Math.min(PARALLEL_POSTS, files.length) }, worker),
        );

        const completed = await flashlightFetch<APICompleteResponse>(
            `/v1/uploads/${encodeURIComponent(kind)}/${encodeURIComponent(started.uploadId)}/complete`,
            {
                init: { method: "POST" },
                errorContext: "Failed to complete upload",
                extra: { kind, fileCount: files.length },
                expectedStatuses: REJECTED_STATUSES,
            },
        );
        return completed.uploadId;
    } catch (error: unknown) {
        throw toRejected(error);
    }
};
