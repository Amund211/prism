import { test, expect, describe } from "vitest";

import { getFlashlightHeaders } from "./flashlight.ts";

describe(getFlashlightHeaders, () => {
    test("identifies rainbow as the client", () => {
        const headers = getFlashlightHeaders();

        expect(headers["X-Client-Type"]).toBe("rainbow");
        expect(headers["X-Client-Version"]).toBe("evergreen");
    });

    test("includes the user id", () => {
        const headers = getFlashlightHeaders();

        expect(headers["X-User-Id"]).toMatch(/^rnb_/);
    });
});
