import { solveChallenge } from "./proofOfWork.ts";
import type { Challenge } from "./proofOfWork.ts";

export type SolveResult =
    | { readonly ok: true; readonly solution: string }
    | { readonly ok: false; readonly error: string };

// globalThis is typed as Window under the DOM lib, whose postMessage takes a
// targetOrigin. In a worker it is the DedicatedWorkerGlobalScope, whose
// postMessage does not.
const post = (result: SolveResult): void => {
    (globalThis as unknown as { postMessage: (message: SolveResult) => void })
        // oxlint-disable-next-line unicorn/require-post-message-target-origin
        .postMessage(result);
};

const handle = async (challenge: Challenge): Promise<void> => {
    try {
        post({ ok: true, solution: await solveChallenge(challenge) });
    } catch (error: unknown) {
        post({
            ok: false,
            error: error instanceof Error ? error.message : String(error),
        });
    }
};

globalThis.addEventListener("message", (event: MessageEvent<Challenge>) => {
    void handle(event.data);
});
