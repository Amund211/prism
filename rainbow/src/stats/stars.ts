// Amount of levels to prestige
const LEVELS_PER_PRESTIGE = 100;

// The exp required to level up once
const LEVEL_COST = 5000;

// The exp required to level up to the first few levels after a prestige
const EASY_LEVEL_COSTS = { 1: 500, 2: 1000, 3: 2000, 4: 3500 };

// The exp required to level up past the easy levels
const EASY_EXP = Object.values(EASY_LEVEL_COSTS).reduce(
    (acc, cost) => acc + cost,
    0,
);

// The amount of easy levels
const EASY_LEVELS = Object.keys(EASY_LEVEL_COSTS).length;

// The exp required to prestige
const PRESTIGE_EXP = EASY_EXP + (100 - EASY_LEVELS) * LEVEL_COST;

/*
 * Return the bedwars level corresponding to the given experience
 *
 * The fractional part represents the progress towards the next level
 *
 * NOTE: Translated from the python implementation in Prism
 */
export const bedwarsLevelFromExp = (exp: number): number => {
    let levels = Math.floor(exp / PRESTIGE_EXP) * LEVELS_PER_PRESTIGE;
    exp %= PRESTIGE_EXP;

    // The first few levels have different costs
    for (let i = 1; i <= EASY_LEVELS; i++) {
        const cost = EASY_LEVEL_COSTS[i as keyof typeof EASY_LEVEL_COSTS];
        if (exp >= cost) {
            levels += 1;
            exp -= cost;
        } else {
            // We can't afford the next level, so we have found the level we are at
            break;
        }
    }
    levels += Math.floor(exp / LEVEL_COST);
    exp %= LEVEL_COST;

    const nextLevel = (levels + 1) % LEVELS_PER_PRESTIGE;

    // The cost of the next level, fallback to LEVEL_COST if it is not an easy level
    let nextLevelCost = LEVEL_COST;
    if (nextLevel in EASY_LEVEL_COSTS) {
        nextLevelCost =
            EASY_LEVEL_COSTS[nextLevel as keyof typeof EASY_LEVEL_COSTS];
    }

    return levels + exp / nextLevelCost;
};
