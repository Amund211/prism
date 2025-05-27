import test from "node:test";
import { newUserId, validateUserId } from "./userId.ts";
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
