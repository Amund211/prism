import test from "node:test";
import { bedwarsLevelFromExp } from "./stars";
import assert from "node:assert";

await test("bedwarsLevelFromExp", async (t) => {
    const cases: { exp: number; stars: number; decimalPrecision: boolean }[] = [
        { exp: 500, stars: 1.0, decimalPrecision: true },
        { exp: 3648, stars: 3 + 148 / 3500, decimalPrecision: true },
        { exp: 89025, stars: 20 + 2025 / 5000, decimalPrecision: true },
        { exp: 122986, stars: 27, decimalPrecision: false },
        { exp: 954638, stars: 196, decimalPrecision: false },
        { exp: 969078, stars: 199, decimalPrecision: false },
        { exp: 975611, stars: 202, decimalPrecision: false },
        { exp: 977587, stars: 203, decimalPrecision: false },
        { exp: 2344717, stars: 481 + 4717 / 5000, decimalPrecision: true },
        { exp: 4870331, stars: 1000 + 331 / 500, decimalPrecision: true },
        { exp: 5316518, stars: 1091 + 4518 / 5000, decimalPrecision: true },
    ];

    for (const { exp, stars, decimalPrecision } of cases) {
        await t.test(exp.toString(), () => {
            const calculatedStar = bedwarsLevelFromExp(exp);

            if (decimalPrecision) {
                assert.strictEqual(
                    calculatedStar,
                    stars,
                    `exp ${exp.toString()} -> ${stars.toString()}`,
                );
            } else {
                assert.strictEqual(
                    Math.floor(calculatedStar),
                    stars,
                    `exp ${exp.toString()} -> ${stars.toString()}`,
                );
            }
        });
    }
});
