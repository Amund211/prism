// The only algorithm flashlight mints challenges for. Unknown values are
// rejected rather than guessed at.
export const POW_ALGORITHM = "sha256-leading-zeros-v1";

// Mirrors flashlight's MaxDifficulty. A server bug must not wedge us in a hash
// loop, so anything above this is an error rather than work.
export const MAX_DIFFICULTY = 26;

const MAX_ATTEMPTS = 2 ** MAX_DIFFICULTY * 8;

// Every candidate costs an async crypto.subtle.digest, and awaiting them one at
// a time caps us around 74k hashes/sec — difficulty 22 would then take ~56s
// against a 60s challengeTTL measured from minting. Overlapping a window of
// them is ~2.4x that, which keeps the whole usable difficulty band reachable.
const BATCH_SIZE = 16;

export interface Challenge {
    readonly challenge: string;
    readonly algorithm: string;
    readonly difficulty: number;
}

const hasLeadingZeroBits = (digest: Uint8Array, bits: number): boolean => {
    let remaining = bits;
    for (const byte of digest) {
        if (remaining <= 0) {
            return true;
        }
        if (remaining < 8) {
            // oxlint-disable-next-line eslint/no-bitwise
            return byte >>> (8 - remaining) === 0;
        }
        if (byte !== 0) {
            return false;
        }
        remaining -= 8;
    }
    return remaining <= 0;
};

/**
 * Find a solution such that SHA-256(`challenge`:`solution`) has at least
 * `difficulty` leading zero bits.
 *
 * Blocks the thread it runs on — call it from the worker unless workers are
 * unavailable.
 */
export const solveChallenge = async ({
    challenge,
    algorithm,
    difficulty,
}: Challenge): Promise<string> => {
    if (algorithm !== POW_ALGORITHM) {
        throw new Error(`Unsupported proof-of-work algorithm: ${algorithm}`);
    }
    if (!Number.isInteger(difficulty) || difficulty < 0) {
        throw new Error(`Invalid proof-of-work difficulty: ${difficulty.toString()}`);
    }
    if (difficulty > MAX_DIFFICULTY) {
        throw new Error(
            `Proof-of-work difficulty above the ceiling: ${difficulty.toString()} > ${MAX_DIFFICULTY.toString()}`,
        );
    }

    const encoder = new TextEncoder();

    for (let base = 0; base < MAX_ATTEMPTS; base += BATCH_SIZE) {
        // Solutions are non-empty even at difficulty 0, where the empty string
        // would be a valid proof. flashlight rejects an empty solution to keep
        // clients from shipping a stub that never implements the hash loop.
        // oxlint-disable-next-line eslint/no-await-in-loop
        const digests = await Promise.all(
            Array.from({ length: BATCH_SIZE }, async (_, offset) =>
                crypto.subtle.digest(
                    "SHA-256",
                    encoder.encode(`${challenge}:${(base + offset).toString()}`),
                ),
            ),
        );

        const hit = digests.findIndex((digest) =>
            hasLeadingZeroBits(new Uint8Array(digest), difficulty),
        );
        if (hit !== -1) {
            // The lowest solution in the batch, so the result does not depend
            // on BATCH_SIZE.
            return (base + hit).toString();
        }
    }

    throw new Error(
        `Failed to solve proof-of-work challenge at difficulty ${difficulty.toString()}`,
    );
};
