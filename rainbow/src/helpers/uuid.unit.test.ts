import { test, expect, describe } from "vitest";
import { normalizeUUID } from "./uuid.ts";

describe(normalizeUUID, () => {
    const cases = [
        {
            // Regular dashed UUID
            input: "01234567-89ab-cdef-0123-456789abcdef",
            expected: "01234567-89ab-cdef-0123-456789abcdef",
        },
        {
            // All caps dashed UUID
            input: "01234567-89AB-CDEF-0123-456789ABCDEF",
            expected: "01234567-89ab-cdef-0123-456789abcdef",
        },
        {
            // Mixed case dashed UUID
            input: "01234567-89ab-cdef-0123-456789ABCDEF",
            expected: "01234567-89ab-cdef-0123-456789abcdef",
        },
        {
            // Regular stripped UUID
            input: "0123456789abcdef0123456789abcdef",
            expected: "01234567-89ab-cdef-0123-456789abcdef",
        },
        {
            // All caps stripped UUID
            input: "0123456789ABCDEF0123456789ABCDEF",
            expected: "01234567-89ab-cdef-0123-456789abcdef",
        },
        {
            // Mixed case stripped UUID
            input: "0123456789ABCDEF0123456789abcdef",
            expected: "01234567-89ab-cdef-0123-456789abcdef",
        },
        {
            // Partially stripped UUID
            input: "01234567-89abcdef-0123456789abcdef",
            expected: "01234567-89ab-cdef-0123-456789abcdef",
        },
        {
            // Weird dashes
            input: "---------0123---------4567-89------------------abcdef-012345---------6789abcdef---------",
            expected: "01234567-89ab-cdef-0123-456789abcdef",
        },
        {
            // Too long
            input: "01234567-89ab-cdef-0123-456789abcdef-0",
            expected: null,
        },
        {
            // Too short
            input: "01234567-89ab-cdef-0123-456789abcde",
            expected: null,
        },
    ];

    for (const tc of cases) {
        test(tc.input, () => {
            const result = normalizeUUID(tc.input);
            expect(result).toBe(tc.expected);
        });
    }
});
