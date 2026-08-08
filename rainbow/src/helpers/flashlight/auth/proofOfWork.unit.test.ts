import { describe, expect, test } from "vitest";

import { MAX_DIFFICULTY, POW_ALGORITHM, solveChallenge } from "./proofOfWork.ts";

const digestBits = async (challenge: string, solution: string): Promise<number> => {
    const digest = new Uint8Array(
        await crypto.subtle.digest(
            "SHA-256",
            new TextEncoder().encode(`${challenge}:${solution}`),
        ),
    );

    let bits = 0;
    for (const byte of digest) {
        if (byte === 0) {
            bits += 8;
            continue;
        }
        bits += Math.clz32(byte) - 24;
        break;
    }
    return bits;
};

describe(solveChallenge, () => {
    test("solves at difficulty 0 with a non-empty solution", async () => {
        const solution = await solveChallenge({
            challenge: "abc",
            algorithm: POW_ALGORITHM,
            difficulty: 0,
        });

        expect(solution.length).toBeGreaterThan(0);
    });

    test("solves at a non-zero difficulty", async () => {
        const challenge = "some-challenge";
        const difficulty = 12;

        const solution = await solveChallenge({
            challenge,
            algorithm: POW_ALGORITHM,
            difficulty,
        });

        await expect(digestBits(challenge, solution)).resolves.toBeGreaterThanOrEqual(
            difficulty,
        );
    });

    test("rejects an unknown algorithm", async () => {
        await expect(
            solveChallenge({
                challenge: "abc",
                algorithm: "sha256-leading-zeros-v2",
                difficulty: 0,
            }),
        ).rejects.toThrow("Unsupported proof-of-work algorithm");
    });

    test("rejects a difficulty above the ceiling", async () => {
        await expect(
            solveChallenge({
                challenge: "abc",
                algorithm: POW_ALGORITHM,
                difficulty: MAX_DIFFICULTY + 1,
            }),
        ).rejects.toThrow("above the ceiling");
    });

    test("rejects a nonsensical difficulty", async () => {
        await expect(
            solveChallenge({
                challenge: "abc",
                algorithm: POW_ALGORITHM,
                difficulty: -1,
            }),
        ).rejects.toThrow("Invalid proof-of-work difficulty");
    });
});
