from prism.overlay.rating import rate_tags
from prism.player import Tags


def test_rate_tags() -> None:
    # Assert the possible tags are ordered in the specified order
    order = (
        Tags(sniping="high", cheating="high"),
        Tags(sniping="high", cheating="medium"),
        Tags(sniping="medium", cheating="high"),
        Tags(sniping="high", cheating="none"),
        Tags(sniping="medium", cheating="medium"),
        Tags(sniping="none", cheating="high"),
        Tags(sniping="medium", cheating="none"),
        Tags(sniping="none", cheating="medium"),
        Tags(sniping="none", cheating="none"),
    )

    assert sorted(reversed(order), key=rate_tags, reverse=True) == list(order)
