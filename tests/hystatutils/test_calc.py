from typing import Union

import pytest

from hystatutils.calc import bedwars_level_from_exp


@pytest.mark.parametrize(
    "exp, true_star",
    [
        (500, 1.0),
        (3648, 3 + 148 / 3500),
        (89025, 20 + 2025 / 5000),
        (122986, 27),
        (954638, 196),
        (969078, 199),
        (975611, 202),
        (977587, 203),
        (2344717, 481 + 4717 / 5000),
        (4870331, 1000 + 331 / 500),
    ],
)
def test_bedwars_star_calculation(exp: int, true_star: Union[int, float]) -> None:
    calculated_star = bedwars_level_from_exp(exp)

    # Compare int with int, and float with float
    if isinstance(true_star, int):
        calculated_star = int(calculated_star)

    assert true_star == calculated_star
