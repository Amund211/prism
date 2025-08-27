from prism.mojang import MojangAccountProvider


def test_make_provider() -> None:
    MojangAccountProvider(retry_limit=3, initial_timeout=1.0)
