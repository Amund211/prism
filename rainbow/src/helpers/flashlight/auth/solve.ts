import { captureMessage } from "@sentry/react";

import { POW_SOLVER_VERSION, solveChallenge } from "./proofOfWork.ts";
import type { Challenge, Solution, SolverReport } from "./proofOfWork.ts";
import type { SolveResult } from "./proofOfWork.worker.ts";

const isSolution = (value: unknown): value is Solution =>
    typeof value === "object" &&
    value !== null &&
    "solution" in value &&
    typeof value.solution === "string" &&
    "hashes" in value &&
    typeof value.hashes === "number" &&
    "elapsedSeconds" in value &&
    typeof value.elapsedSeconds === "number";

export interface SolvedChallenge {
    readonly solution: string;
    readonly solver: SolverReport;
}

const withSolver = (
    name: SolverReport["name"],
    { solution, hashes, elapsedSeconds }: Solution,
): SolvedChallenge => ({
    solution,
    solver: { name, version: POW_SOLVER_VERSION, hashes, elapsedSeconds },
});

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

const awaitSolution = async (worker: Worker, challenge: Challenge): Promise<Solution> =>
    // A worker only speaks in events, so this bridge has to be a new promise
    // oxlint-disable-next-line promise/avoid-new
    new Promise<Solution>((resolve, reject) => {
        worker.addEventListener("message", (event: MessageEvent<SolveResult>) => {
            const result = event.data;
            if (result.ok) {
                if (isSolution(result.result)) {
                    resolve(result.result);
                } else {
                    // A stale cached worker from another release
                    reject(
                        new WorkerFailedError(
                            "The proof-of-work worker sent a malformed result",
                        ),
                    );
                }
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
 *
 * The report names the path that did the work: "worker" or "inline".
 */
export const solve = async (challenge: Challenge): Promise<SolvedChallenge> => {
    const worker = createWorker();
    if (worker === null) {
        return withSolver("inline", await solveChallenge(challenge));
    }

    try {
        return withSolver("worker", await awaitSolution(worker, challenge));
    } catch (error: unknown) {
        if (!(error instanceof WorkerFailedError)) {
            throw error;
        }
        captureMessage("The proof-of-work worker failed — solving on the main thread", {
            level: "warning",
            extra: { error },
        });
        return withSolver("inline", await solveChallenge(challenge));
    } finally {
        worker.terminate();
    }
};
