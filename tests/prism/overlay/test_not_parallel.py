from prism.overlay.not_parallel import ensure_not_parallel


def test_not_parallel() -> None:
    ensure_not_parallel()

    # Can't get this to work
    """
    # HACK: Pretend we have two instances launced
    # Need to store the current singleton so it doesn't get released
    from prism.overlay.not_parallel import SINGLEINSTANCE_LOCK

    _ = SINGLEINSTANCE_LOCK
    with pytest.raises(SystemExit):
        ensure_not_parallel()
    """
