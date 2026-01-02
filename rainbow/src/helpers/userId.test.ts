import test from "node:test";
import {
    LOCAL_DEVELOPMENT_USER_ID,
    newUserId,
    STAGING_USER_ID,
    validateUserId,
} from "./userId.ts";
import assert from "node:assert";
import { isNormalizedUUID } from "./uuid.ts";

await test("newUserId", async (t) => {
    await t.test(
        "should generate a new user ID like rnb_<uuid-v4>",
        async (t) => {
            for (let i = 0; i < 10; i++) {
                const userId = newUserId();
                await t.test(userId, () => {
                    assert.ok(
                        userId.startsWith("rnb_"),
                        "User ID should start with 'rnb_'",
                    );

                    const suffix = userId.slice(4);

                    assert.ok(
                        isNormalizedUUID(suffix),
                        "User ID suffix should be a normalized UUID",
                    );
                });
            }
        },
    );

    await t.test(
        "should generate a new user ID that passes validation",
        async (t) => {
            for (let i = 0; i < 10; i++) {
                const userId = newUserId();
                await t.test(userId, () => {
                    assert.ok(
                        validateUserId(userId),
                        "User ID should be valid",
                    );
                });
            }
        },
    );

    await t.test("without crypto.randomUUID", async (t) => {
        let originalRandomUUID: typeof crypto.randomUUID | undefined;
        t.before(() => {
            originalRandomUUID = crypto.randomUUID.bind(crypto);

            // Simulate an environment without crypto.randomUUID
            crypto.randomUUID =
                undefined as unknown as typeof crypto.randomUUID;
        });
        t.after(() => {
            assert.ok(
                originalRandomUUID,
                "crypto.randomUUID should be restored after the test",
            );
            crypto.randomUUID = originalRandomUUID;
        });

        await t.test(
            "should generate a new user ID like rnb_<random-string>",
            async (t) => {
                for (let i = 0; i < 10; i++) {
                    const userId = newUserId();
                    await t.test(userId, () => {
                        assert.ok(
                            userId.startsWith("rnb_"),
                            "User ID should start with 'rnb_'",
                        );

                        const suffix = userId.slice(4);

                        assert.ok(
                            /^([a-f0-9-]+-){3}([a-f0-9-]+)$/.test(suffix),
                            "User ID suffix should be a four random hex strings",
                        );

                        assert.strictEqual(
                            suffix.split("-").length,
                            4,
                            "User ID suffix should consist of 4 parts",
                        );

                        for (const part of suffix.split("-")) {
                            assert.strictEqual(
                                part.length,
                                12,
                                "Each part of the user ID suffix should be 12 characters long",
                            );
                        }
                    });
                }
            },
        );

        await t.test(
            "should generate a new user ID that passes validation",
            async (t) => {
                for (let i = 0; i < 10; i++) {
                    const userId = newUserId();
                    await t.test(userId, () => {
                        assert.ok(
                            validateUserId(userId),
                            "User ID should be valid",
                        );
                    });
                }
            },
        );
    });
});

await test("getOrSetUserId", async (t) => {
    await t.test("in development mode", () => {
        // We use import.meta.env.DEV to return this from getOrSetUserId(), so we can't test
        // in node. Instead we just do some basic checks on the exported constant.
        assert.ok(
            validateUserId(LOCAL_DEVELOPMENT_USER_ID),
            "Development user ID should be valid",
        );

        assert.ok(
            LOCAL_DEVELOPMENT_USER_ID.startsWith("rnb_"),
            "Development user ID should start with 'rnb_'",
        );

        assert.strictEqual(LOCAL_DEVELOPMENT_USER_ID, "rnb_local_development");
    });

    await t.test("in staging", () => {
        // We use the current hostname to return this from getOrSetUserId(), so we don't test
        // this here. Instead we just do some basic checks on the exported constant.
        assert.ok(
            validateUserId(STAGING_USER_ID),
            "Staging user ID should be valid",
        );

        assert.ok(
            STAGING_USER_ID.startsWith("rnb_"),
            "Staging user ID should start with 'rnb_'",
        );

        assert.strictEqual(STAGING_USER_ID, "rnb_staging");
    });
});

await test("validateUserId", async (t) => {
    const cases = [
        {
            input: "rnb_4a6113bb-5f94-4bc6-9e71-fc94e90c1fb2",
            expected: true,
        },
        {
            input: "rnb_custom_suffix",
            expected: true,
        },
        {
            input: "rnb_local_development",
            expected: true,
        },
        {
            input: LOCAL_DEVELOPMENT_USER_ID,
            expected: true,
        },
        {
            input: null,
            expected: false,
        },
        {
            input: "invalid_prefix_0123456789abcdef0123456789abcdef",
            expected: false,
        },
        {
            input: "Rnb_invalid_prefix",
            expected: false,
        },
    ];

    for (const tc of cases) {
        await t.test(tc.input ?? "<null>", () => {
            const result = validateUserId(tc.input);
            assert.strictEqual(result, tc.expected);
        });
    }
});
