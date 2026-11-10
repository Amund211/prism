import { createHash } from "node:crypto";

import { describe, expect, test } from "vitest";

import { challengeFor, createVerifier, signInErrorMessage } from "./microsoft.ts";

// The formats flashlight accepts.
const VERIFIER_RX = /^[A-Za-z0-9._~-]{43,128}$/;
const CHALLENGE_RX = /^[A-Za-z0-9_-]{43}$/;

describe(createVerifier, () => {
    test("matches the contract and is 32 random bytes", () => {
        const verifier = createVerifier();

        expect(verifier).toMatch(VERIFIER_RX);
        expect(verifier).toHaveLength(43);
        expect(createVerifier()).not.toBe(verifier);
    });
});

describe(challengeFor, () => {
    test("is base64url(sha256(verifier)) without padding", async () => {
        const verifier = createVerifier();

        const challenge = await challengeFor(verifier);

        expect(challenge).toMatch(CHALLENGE_RX);
        expect(challenge).toBe(
            createHash("sha256").update(verifier).digest("base64url"),
        );
    });
});

describe(signInErrorMessage, () => {
    test.for([
        ["client_not_approved", "Microsoft sign-in is not available yet."],
        ["no_game", "This Microsoft account does not own Minecraft Java Edition."],
        ["no_profile", "This Microsoft account does not own Minecraft Java Edition."],
        [
            "no_xbox_account",
            "This Microsoft account has no Xbox profile. Sign in once at xbox.com, then try again.",
        ],
        ["child_account", "Xbox needs an adult to approve this account."],
        ["adult_verification_required", "Xbox needs an adult to approve this account."],
        ["xbox_unavailable_in_region", "Xbox Live is not available in your region."],
        ["microsoft_error", "Sign-in was cancelled."],
        ["flow_missing", "Sign-in expired. Try again."],
        ["flow_invalid", "Sign-in expired. Try again."],
        ["flow_expired", "Sign-in expired. Try again."],
        ["state_mismatch", "Sign-in expired. Try again."],
        ["code_rejected", "Sign-in expired. Try again."],
        ["invalid_callback", "Sign-in expired. Try again."],
        ["temporarily_unavailable", "Sign-in failed. Try again later."],
        ["xbox_refused", "Sign-in failed. Try again later."],
        ["internal_error", "Sign-in failed. Try again later."],
        ["something_new", "Sign-in failed. Try again later."],
        ["toString", "Sign-in failed. Try again later."],
    ])("maps %s", ([code, message]) => {
        expect(signInErrorMessage(code)).toBe(message);
    });
});
