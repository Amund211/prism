import { captureMessage } from "@sentry/react";

import { solveChallenge } from "./proofOfWork.ts";
import type { Challenge } from "./proofOfWork.ts";
import type { SolveResult } from "./proofOfWork.worker.ts";

/**
 * The worker could not run at all — as opposed to running and reporting that it
 * could not solve the challenge. Only the former is safe to retry inline.
 */
class WorkerFailedError extends Error {
    public override name = "WorkerFailedError";
}

const createWorker = (): Worker | null => {
    if (typeof Worker === "undefined") {
        return null;
    }
    try {
        // Vite resolves this exact pattern at build time — keep the "./" prefix
        // oxlint-disable-next-line unicorn/relative-url-style
        return new Worker(new URL("./proofOfWork.worker.ts", import.meta.url), {
            type: "module",
        });
    } catch (error: unknown) {
        captureMessage("Failed to create the proof-of-work worker", {
            level: "warning",
            extra: { error },
        });
        return null;
    }
};

const awaitSolution = async (worker: Worker, challenge: Challenge): Promise<string> =>
    // A worker only speaks in events, so this bridge has to be a new promise
    // oxlint-disable-next-line promise/avoid-new
    new Promise<string>((resolve, reject) => {
        worker.addEventListener("message", (event: MessageEvent<SolveResult>) => {
            const result = event.data;
            if (result.ok) {
                resolve(result.solution);
            } else {
                reject(new Error(result.error));
            }
        });
        // ErrorEvent carries an `error: any`, which the rule cannot prove readonly
        // oxlint-disable-next-line typescript/prefer-readonly-parameter-types
        worker.addEventListener("error", (event: ErrorEvent) => {
            // Cross-origin scripts scrub this to "Script error." with no filename
            reject(
                new WorkerFailedError(
                    `The proof-of-work worker failed to run: ${event.message} (${event.filename}:${event.lineno}:${event.colno})`,
                ),
            );
        });
        // Without this listener a challenge that fails structured clone never settles
        worker.addEventListener("messageerror", () => {
            reject(
                new WorkerFailedError(
                    "The proof-of-work challenge did not reach the worker",
                ),
            );
        });
        // Worker.postMessage takes no targetOrigin
        // oxlint-disable-next-line unicorn/require-post-message-target-origin
        worker.postMessage(challenge);
    });

/**
 * Solve a proof-of-work challenge off the hot path.
 *
 * Falls back to the main thread wherever the worker cannot run — unavailable,
 * unconstructable, or failing to load — since the work is one hash at the
 * current difficulty of 0. A worker that runs and reports that it could not
 * solve the challenge is not retried: that verdict holds on any thread, and
 * inline retries of a too-hard challenge would freeze the tab instead.
 */
export const solve = async (challenge: Challenge): Promise<string> => {
    const worker = createWorker();
    if (worker === null) {
        return solveChallenge(challenge);
    }

    try {
        return await awaitSolution(worker, challenge);
    } catch (error: unknown) {
        if (!(error instanceof WorkerFailedError)) {
            throw error;
        }
        captureMessage("The proof-of-work worker failed — solving on the main thread", {
            level: "warning",
            extra: { error },
        });
        return await solveChallenge(challenge);
    } finally {
        worker.terminate();
    }
};
