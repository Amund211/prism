import { captureException } from "@sentry/react";

import { env } from "#env.ts";
import { FlashlightResponseError } from "#helpers/flashlight/request.ts";

import { exchangeMicrosoftResult } from "./api.ts";
import { adoptSession } from "./session.ts";
import type { Session } from "./storage.ts";

const VERIFIER_SESSION_STORAGE_KEY = "rainbow_ms_verifier";

const CALLBACK_PATH = "/auth/microsoft";

/**
 * Whether this page load is the Microsoft callback, with its fragment.
 */
export const isMicrosoftCallback = (): boolean =>
    location.pathname === CALLBACK_PATH && location.hash !== "";

const EXPIRED_MESSAGE = "Sign-in expired. Try again.";
const FAILED_MESSAGE = "Sign-in failed. Try again later.";
const NO_GAME_MESSAGE = "This Microsoft account does not own Minecraft Java Edition.";
const ADULT_MESSAGE = "Xbox needs an adult to approve this account.";

const ERROR_MESSAGES: ReadonlyMap<string, string> = new Map([
    ["client_not_approved", "Microsoft sign-in is not available yet."],
    ["no_game", NO_GAME_MESSAGE],
    ["no_profile", NO_GAME_MESSAGE],
    [
        "no_xbox_account",
        "This Microsoft account has no Xbox profile. Sign in once at xbox.com, then try again.",
    ],
    ["child_account", ADULT_MESSAGE],
    ["adult_verification_required", ADULT_MESSAGE],
    ["xbox_unavailable_in_region", "Xbox Live is not available in your region."],
    ["microsoft_error", "Sign-in was cancelled."],
    ["flow_missing", EXPIRED_MESSAGE],
    ["flow_invalid", EXPIRED_MESSAGE],
    ["flow_expired", EXPIRED_MESSAGE],
    ["state_mismatch", EXPIRED_MESSAGE],
    ["code_rejected", EXPIRED_MESSAGE],
    ["invalid_callback", EXPIRED_MESSAGE],
]);

const NOT_RETRYABLE: ReadonlySet<string> = new Set([
    "client_not_approved",
    "no_game",
    "no_profile",
    "child_account",
    "adult_verification_required",
    "xbox_unavailable_in_region",
]);

/**
 * The user-facing message for a callback `error=` code.
 */
export const signInErrorMessage = (code: string): string =>
    ERROR_MESSAGES.get(code) ?? FAILED_MESSAGE;

const base64url = (bytes: Uint8Array): string =>
    btoa(String.fromCodePoint(...bytes))
        .replaceAll("+", "-")
        .replaceAll("/", "_")
        .replace(/[=]+$/, "");

/**
 * A new PKCE verifier: 32 random bytes, base64url without padding (43 chars).
 */
export const createVerifier = (): string =>
    base64url(crypto.getRandomValues(new Uint8Array(32)));

/**
 * The PKCE challenge for `verifier`: base64url(sha256(verifier)), no padding.
 */
export const challengeFor = async (verifier: string): Promise<string> => {
    const digest = await crypto.subtle.digest(
        "SHA-256",
        new TextEncoder().encode(verifier),
    );
    return base64url(new Uint8Array(digest));
};

const storeVerifier = (verifier: string): boolean => {
    try {
        sessionStorage.setItem(VERIFIER_SESSION_STORAGE_KEY, verifier);
        return true;
    } catch (error: unknown) {
        captureException(error, {
            extra: { message: "Failed to store the sign-in verifier" },
        });
        return false;
    }
};

const takeVerifier = (): string | null => {
    try {
        const verifier = sessionStorage.getItem(VERIFIER_SESSION_STORAGE_KEY);
        sessionStorage.removeItem(VERIFIER_SESSION_STORAGE_KEY);
        return verifier;
    } catch (error: unknown) {
        captureException(error, {
            extra: { message: "Failed to read the sign-in verifier" },
        });
        return null;
    }
};

/**
 * Store a new verifier and return the flashlight URL that starts the sign-in.
 *
 * Throws if the verifier cannot be stored: the sign-in could not finish.
 */
export const prepareMicrosoftSignIn = async (): Promise<string> => {
    const verifier = createVerifier();
    const challenge = await challengeFor(verifier);
    if (!storeVerifier(verifier)) {
        throw new Error("Could not store the sign-in verifier");
    }
    const params = new URLSearchParams({ return: location.origin, challenge });
    return `${env.VITE_FLASHLIGHT_URL}/v1/auth/microsoft/start?${params.toString()}`;
};

/**
 * Leave the page to sign in with Microsoft. flashlight returns to
 * /auth/microsoft.
 */
export const startMicrosoftSignIn = async (): Promise<void> => {
    location.assign(await prepareMicrosoftSignIn());
};

/**
 * The result of a sign-in callback. `retryable` is false when starting again
 * cannot help, such as an account without the game.
 */
export type SignInOutcome =
    | { readonly kind: "signedIn"; readonly session: Session }
    | {
          readonly kind: "failed";
          readonly message: string;
          readonly retryable: boolean;
      };

const failed = (message: string, retryable = true): SignInOutcome => ({
    kind: "failed",
    message,
    retryable,
});

const complete = async (params: Readonly<URLSearchParams>): Promise<SignInOutcome> => {
    const verifier = takeVerifier();

    const code = params.get("error");
    if (code !== null) {
        return failed(signInErrorMessage(code), !NOT_RETRYABLE.has(code));
    }

    const result = params.get("result");
    if (result === null || verifier === null) {
        return failed(EXPIRED_MESSAGE);
    }

    try {
        const session = await exchangeMicrosoftResult(result, verifier);
        return { kind: "signedIn", session: await adoptSession(session) };
    } catch (error: unknown) {
        if (error instanceof FlashlightResponseError && error.status === 401) {
            return failed(EXPIRED_MESSAGE);
        }
        return failed(FAILED_MESSAGE);
    }
};

let callback: Promise<SignInOutcome> | null = null;

/**
 * Finish the sign-in from the /auth/microsoft callback fragment.
 *
 * Removes the fragment from the URL at once. Safe to call again on the same
 * page load (effects can run twice): later calls get the same outcome.
 */
export const finishMicrosoftSignIn = async (): Promise<SignInOutcome> => {
    const { hash, pathname } = location;
    if (hash !== "") {
        history.replaceState(history.state, "", pathname);
        callback = complete(new URLSearchParams(hash.slice(1)));
    }
    return callback ?? failed(EXPIRED_MESSAGE);
};
