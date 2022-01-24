"""
Module from calculating bedwars star from exp
"""
# Amount of levels to prestige
LEVELS_PER_PRESTIGE = 100

# The exp required to level up once
LEVEL_COST = 5000

# The exp required to level up to the first few levels after a prestige
EASY_LEVEL_COSTS = {1: 500, 2: 1000, 3: 2000, 4: 3500}

# The exp required to level up past the easy levels
EASY_EXP = sum(EASY_LEVEL_COSTS.values())

# The amount of easy levels
EASY_LEVELS = len(EASY_LEVEL_COSTS)

# The exp required to prestige
PRESTIGE_EXP = EASY_EXP + (100 - EASY_LEVELS) * LEVEL_COST


def bedwars_level_from_exp(exp: int) -> float:
    """
    Return the bedwars level corresponding to the given experience

    The fractional part represents the progress towards the next level
    """
    levels = (exp // PRESTIGE_EXP) * LEVELS_PER_PRESTIGE
    exp %= PRESTIGE_EXP

    # The first few levels have different costs
    for i in range(1, EASY_LEVELS + 1):
        cost = EASY_LEVEL_COSTS[i]
        if exp >= cost:
            levels += 1
            exp -= cost
        else:
            # We can't afford the next level, so we have found the level we are at
            break

    levels += exp // LEVEL_COST
    exp %= LEVEL_COST

    next_level = (levels + 1) % LEVELS_PER_PRESTIGE

    # The cost of the next level
    if next_level in EASY_LEVEL_COSTS:
        next_level_cost = EASY_LEVEL_COSTS[next_level]
    else:
        next_level_cost = LEVEL_COST

    return levels + exp / next_level_cost
