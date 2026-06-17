from prism.overlay.current_player import CurrentPlayerThread
from tests.prism.overlay.utils import (
    assert_controllers_equal,
    create_controller,
    create_state,
    make_player,
)


def test_current_player_thread_init() -> None:
    controller = create_controller()

    def sleep_mock(_: float) -> None:
        pass

    thread = CurrentPlayerThread(controller=controller, sleep=sleep_mock, timeout=10)
    assert thread.controller == controller
    assert thread.sleep == sleep_mock
    assert thread.timeout == 10
    assert thread.username is None
    assert thread.previous_player is None


def test_regular_processing_order() -> None:
    controller = create_controller(
        state=create_state(
            own_username="Main",
        ),
    )

    main = make_player("player", "Main", wins=10)
    main_after_game = make_player("player", "Main", wins=11)  # Different wins count
    alt = make_player("player", "Alt", wins=11)
    sleep_calls: list[float] = []
    sleep_count = 0

    def sleep(duration: float) -> None:
        nonlocal sleep_count
        sleep_calls.append(duration)
        # We simulate the stats thread fetching the player data in the background by
        # populating the cache after one sleep
        if sleep_count == 0:
            # First sleep: initial username change
            controller.player_cache.set_cached_player(
                "Main", main, genus=controller.player_cache.current_genus
            )
        elif sleep_count == 1:
            # Second sleep (sleep(5) after game end): player has updated stats
            controller.player_cache.set_cached_player(
                "Main", main_after_game, genus=controller.player_cache.current_genus
            )
        elif sleep_count == 2:
            # Third sleep: account swap to Alt
            controller.player_cache.set_cached_player(
                "Alt", alt, genus=controller.player_cache.current_genus
            )
        sleep_count += 1
        return None

    thread = CurrentPlayerThread(controller=controller, sleep=sleep, timeout=0)

    # Initial process should cause one update, since we have a new username
    thread.process_updates()

    assert_controllers_equal(
        controller,
        create_controller(
            state=create_state(
                own_username="Main",
            ),
            current_player_updates=(main,),
        ),
        ignore_player_cache=True,
    )

    # Assert sleep was called with duration 1 (waiting for player data)
    assert sleep_calls == [1]
    sleep_calls.clear()

    # Simulate player updates being picked up
    controller.current_player_updates_queue.get_nowait()

    # Second process should do nothing, since the username hasn't changed, and no
    # game has ended
    thread.process_updates()
    thread.process_updates()
    thread.process_updates()
    thread.process_updates()
    thread.process_updates()

    assert_controllers_equal(
        controller,
        create_controller(
            state=create_state(
                own_username="Main",
            ),
            current_player_updates=(),
        ),
        ignore_player_cache=True,
    )

    # No sleep should have been called during these updates
    assert sleep_calls == []

    # Simulate a game ending by changing the state
    controller.game_ended_event.set()

    # Update should trigger an update since a game ended
    thread.process_updates()

    assert_controllers_equal(
        controller,
        create_controller(
            state=create_state(
                own_username="Main",
            ),
            current_player_updates=(main_after_game,),
        ),
        ignore_player_cache=True,
    )

    # Assert event cleared
    assert not controller.game_ended_event.is_set()

    # Assert sleep was called with duration 5 (wait for Hypixel API update)
    # Player is already in cache from the sleep(5), so no additional sleep(1) needed
    assert sleep_calls == [5]

    sleep_calls.clear()
    controller.current_player_updates_queue.get_nowait()

    controller.state = create_state(own_username="Alt")

    # Should detect account swap
    thread.process_updates()

    assert_controllers_equal(
        controller,
        create_controller(
            state=create_state(
                own_username="Alt",
            ),
            current_player_updates=(alt,),
        ),
        ignore_player_cache=True,
    )

    # Assert sleep was called with duration 1 (waiting for player data)
    assert sleep_calls == [1]


def test_username_is_none() -> None:
    """
    Test that processing stops early when username is None

    NOTE: It must still sleep before returning. run() calls process_updates() in a
          tight `while True` loop, so a path that returns without blocking pins a CPU
          core at 100%. This happens for the entire session whenever the log parser
          never detects the client's username (e.g. an unrecognized "Setting user"
          line, or the overlay tailing past it after a log rotation).
    """
    controller = create_controller(
        state=create_state(
            own_username=None,  # No username set
        ),
    )

    sleep_calls: list[float] = []

    def sleep(duration: float) -> None:
        sleep_calls.append(duration)

    thread = CurrentPlayerThread(controller=controller, sleep=sleep, timeout=15)

    # Process should do nothing but sleep when username is None
    thread.process_updates()

    # No updates should be queued
    assert_controllers_equal(
        controller,
        create_controller(
            state=create_state(
                own_username=None,
            ),
            current_player_updates=(),
        ),
        ignore_player_cache=True,
    )

    # We must sleep for the poll interval to avoid busy-looping in run()
    assert sleep_calls == [15]


def test_username_stays_none_does_not_busy_loop() -> None:
    """
    Repeatedly processing with no username must sleep on every iteration.

    This is the primary prod busy-loop: run() spins process_updates() forever, and
    when own_username is None every iteration must block, or one CPU core is pinned.
    """
    controller = create_controller(
        state=create_state(
            own_username=None,
        ),
    )

    sleep_calls: list[float] = []

    def sleep(duration: float) -> None:
        sleep_calls.append(duration)

    thread = CurrentPlayerThread(controller=controller, sleep=sleep, timeout=15)

    for _ in range(5):
        thread.process_updates()

    # Every iteration must have slept - no busy loop
    assert sleep_calls == [15] * 5


def test_username_none_with_game_ended_set_still_sleeps() -> None:
    """
    A stale game_ended_event must not let the no-username path skip its sleep.

    Guards against a future change adding event handling to the no-username path
    that could return early (without blocking) when the event happens to be set.
    """
    controller = create_controller(
        state=create_state(
            own_username=None,
        ),
    )

    # Stale event set while we still have no username
    controller.game_ended_event.set()

    sleep_calls: list[float] = []

    def sleep(duration: float) -> None:
        sleep_calls.append(duration)

    thread = CurrentPlayerThread(controller=controller, sleep=sleep, timeout=15)

    thread.process_updates()
    thread.process_updates()

    assert sleep_calls == [15, 15]


def test_username_change_to_none() -> None:
    """
    Test that username change from a value to None is handled

    After the username clears, subsequent iterations converge on the stable
    no-username state, which must keep sleeping rather than busy-looping.
    """
    controller = create_controller(
        state=create_state(
            own_username="Main",
        ),
    )

    main = make_player("player", "Main")
    sleep_calls: list[float] = []

    def sleep(duration: float) -> None:
        sleep_calls.append(duration)
        # Simulate the stats thread fetching the player data
        controller.player_cache.set_cached_player(
            "Main", main, genus=controller.player_cache.current_genus
        )

    thread = CurrentPlayerThread(controller=controller, sleep=sleep, timeout=15)

    # Initial process should cause one update
    thread.process_updates()
    assert thread.username == "Main"

    # Clear the queue
    controller.current_player_updates_queue.get_nowait()
    sleep_calls.clear()

    # Change username to None
    controller.state = create_state(own_username=None)

    # Process should handle the username change to None
    thread.process_updates()

    # Username should be updated to None
    assert thread.username is None

    # The transition iteration must sleep to avoid busy-looping
    assert sleep_calls == [15]

    # Further iterations in the stable no-username state must keep sleeping
    sleep_calls.clear()
    thread.process_updates()
    thread.process_updates()
    assert sleep_calls == [15, 15]


def test_idle_known_username_waits_on_game_ended_event() -> None:
    """
    The idle (known username, no game ended) path must not busy-loop either.

    Unlike the no-username path, it is paced by blocking on game_ended_event.wait()
    for the poll interval. This guards that pacing so a refactor can't drop it.
    """
    controller = create_controller(
        state=create_state(
            own_username="Main",
        ),
    )

    main = make_player("player", "Main")
    controller.player_cache.set_cached_player(
        "Main", main, genus=controller.player_cache.current_genus
    )

    wait_calls: list[float | None] = []

    def fake_wait(timeout: float | None = None) -> bool:
        wait_calls.append(timeout)
        return False  # No game ended

    # Shadow the bound method on this Event instance
    controller.game_ended_event.wait = fake_wait  # type: ignore[method-assign]

    sleep_calls: list[float] = []

    thread = CurrentPlayerThread(
        controller=controller, sleep=sleep_calls.append, timeout=15
    )

    # First call establishes the username (name_changed path, no idle wait)
    thread.process_updates()
    assert thread.username == "Main"
    assert wait_calls == []

    # Subsequent idle calls must block on the event for the poll interval
    thread.process_updates()
    thread.process_updates()

    assert wait_calls == [15, 15]


def test_name_change_then_same_name_does_not_busy_loop() -> None:
    """
    A name change must advance state so it isn't re-entered forever.

    The name-changed path produces no sleep when get_player hits a warm cache. It
    avoids busy-looping only because `self.username` is updated to the new name, so
    the next iteration is no longer name_changed and falls through to the blocking
    idle path. This guards that guarantee: if the username assignment were ever
    dropped, name_changed would stay True every iteration and (with a warm cache)
    spin a CPU core with no sleep.
    """
    controller = create_controller(
        state=create_state(
            own_username="Main",
        ),
    )

    # Pre-cache the player so get_player returns immediately - the worst case,
    # since the name-changed path then performs no sleep of its own.
    main = make_player("player", "Main", wins=10)
    controller.player_cache.set_cached_player(
        "Main", main, genus=controller.player_cache.current_genus
    )

    wait_calls: list[float | None] = []

    def fake_wait(timeout: float | None = None) -> bool:
        wait_calls.append(timeout)
        return False  # No game ended

    controller.game_ended_event.wait = fake_wait  # type: ignore[method-assign]

    sleep_calls: list[float] = []

    thread = CurrentPlayerThread(
        controller=controller, sleep=sleep_calls.append, timeout=15
    )

    # Name change is handled once: username advances, an update is queued, and -
    # because the cache is warm - it neither sleeps nor waits on the event.
    thread.process_updates()

    assert thread.username == "Main"
    assert sleep_calls == []
    assert wait_calls == []
    assert_controllers_equal(
        controller,
        create_controller(
            state=create_state(own_username="Main"),
            current_player_updates=(main,),
        ),
        ignore_player_cache=True,
    )

    # Drain the queued update
    controller.current_player_updates_queue.get_nowait()

    # Holding the same name for a while must take the blocking idle path every time
    # (no busy loop) and must not re-fire the name-changed handling.
    for _ in range(3):
        thread.process_updates()

    assert sleep_calls == []
    assert wait_calls == [15, 15, 15]
    # No further updates queued - name_changed was not re-entered
    assert_controllers_equal(
        controller,
        create_controller(
            state=create_state(own_username="Main"),
            current_player_updates=(),
        ),
        ignore_player_cache=True,
    )


def test_get_player_returns_none_on_name_changed() -> None:
    """Test that processing stops when get_player returns None on name change"""
    controller = create_controller(
        state=create_state(
            own_username="Main",
        ),
    )

    sleep_calls: list[float] = []

    def sleep(duration: float) -> None:
        sleep_calls.append(duration)
        # Don't populate the cache - simulating player data not being available

    thread = CurrentPlayerThread(controller=controller, sleep=sleep, timeout=0)

    # Process should try to get player but fail (times out after 60 sleeps)
    thread.process_updates()

    # Should have tried 60 times with sleep(1)
    assert sleep_calls == [1] * 60

    # No updates should be queued since player data wasn't available
    assert_controllers_equal(
        controller,
        create_controller(
            state=create_state(
                own_username="Main",
            ),
            current_player_updates=(),
        ),
        ignore_player_cache=True,
    )


def test_get_player_returns_none_on_game_ended() -> None:
    """Test that processing stops when get_player returns None on game end"""
    controller = create_controller(
        state=create_state(
            own_username="Main",
        ),
    )

    main = make_player("player", "Main", wins=5)
    sleep_calls: list[float] = []
    initial_setup_done = False

    def sleep(duration: float) -> None:
        nonlocal initial_setup_done
        sleep_calls.append(duration)
        # Populate cache only during initial setup
        if not initial_setup_done:
            controller.player_cache.set_cached_player(
                "Main", main, genus=controller.player_cache.current_genus
            )
            initial_setup_done = True

    thread = CurrentPlayerThread(controller=controller, sleep=sleep, timeout=0)

    # Initial process should succeed
    thread.process_updates()
    controller.current_player_updates_queue.get_nowait()
    sleep_calls.clear()

    # Clear the cache (simulating cache invalidation)
    controller.player_cache.clear_cache()

    # Simulate a game ending
    controller.game_ended_event.set()

    # Process should try to get player but fail after timeout
    thread.process_updates()

    # Should have slept 5 seconds, then tried 60 times with sleep(1)
    assert sleep_calls == [5] + [1] * 60

    # No new updates should be queued since player data wasn't available
    assert_controllers_equal(
        controller,
        create_controller(
            state=create_state(
                own_username="Main",
            ),
            current_player_updates=(),
        ),
        ignore_player_cache=True,
    )


def test_game_ended_with_no_previous_player() -> None:
    """Test that processing stops when game ends but previous_player is None"""
    controller = create_controller(
        state=create_state(
            own_username="Main",
        ),
    )

    main = make_player("player", "Main")
    sleep_calls: list[float] = []

    def sleep(duration: float) -> None:
        sleep_calls.append(duration)
        # Always return the player
        controller.player_cache.set_cached_player(
            "Main", main, genus=controller.player_cache.current_genus
        )

    thread = CurrentPlayerThread(controller=controller, sleep=sleep, timeout=0)

    # Set thread to have a username but no previous_player
    thread.username = "Main"
    thread.previous_player = None

    # Simulate a game ending
    controller.game_ended_event.set()

    sleep_calls.clear()

    # Process should handle game end but stop early since previous_player is None
    thread.process_updates()

    # Should have slept 5 seconds and then once to get player
    assert sleep_calls == [5]

    # Should have queued one update
    assert_controllers_equal(
        controller,
        create_controller(
            state=create_state(
                own_username="Main",
            ),
            current_player_updates=(main,),
        ),
        ignore_player_cache=True,
    )


def test_game_ended_stats_unchanged_then_changed() -> None:
    """Test the retry logic when stats don't change after a game"""
    controller = create_controller(
        state=create_state(
            own_username="Main",
        ),
    )

    main = make_player("player", "Main", wins=10)
    main_updated = make_player("player", "Main", wins=11)  # Updated wins
    sleep_calls: list[float] = []

    def sleep(duration: float) -> None:
        sleep_calls.append(duration)
        # On first sleep (initial name change), return main
        if len(sleep_calls) == 1:
            controller.player_cache.set_cached_player(
                "Main", main, genus=controller.player_cache.current_genus
            )
        # On sleep(65), update cache to have new data
        elif len(sleep_calls) == 2:
            # This is the sleep(65), after which we want updated data
            controller.player_cache.set_cached_player(
                "Main", main_updated, genus=controller.player_cache.current_genus
            )

    thread = CurrentPlayerThread(controller=controller, sleep=sleep, timeout=0)

    # Initial process
    thread.process_updates()
    controller.current_player_updates_queue.get_nowait()
    sleep_calls.clear()

    # Simulate a game ending
    controller.game_ended_event.set()

    # Process should detect unchanged stats and retry
    thread.process_updates()

    # Should have: sleep(5), then detect stale (main has same wins as
    # previous), sleep(65)
    assert sleep_calls == [5, 65]

    # Should have queued main (same wins as before, so detected as stale)
    assert_controllers_equal(
        controller,
        create_controller(
            state=create_state(
                own_username="Main",
            ),
            current_player_updates=(main, main_updated),
        ),
        ignore_player_cache=True,
    )

    # previous_player should be updated to the final one (from retry)
    assert thread.previous_player == main_updated


def test_game_ended_stats_unchanged_retry_fails() -> None:
    """Test when stats don't change and the retry also times out"""
    controller = create_controller(
        state=create_state(
            own_username="Main",
        ),
    )

    main = make_player("player", "Main", wins=10)
    sleep_calls: list[float] = []

    def sleep(duration: float) -> None:
        sleep_calls.append(duration)
        if len(sleep_calls) == 1:
            # Initial name change
            controller.player_cache.set_cached_player(
                "Main", main, genus=controller.player_cache.current_genus
            )
        elif len(sleep_calls) == 2:
            # After sleep(65), clear cache so get_player times out
            controller.player_cache.clear_cache()

    thread = CurrentPlayerThread(controller=controller, sleep=sleep, timeout=0)

    # Initial process
    thread.process_updates()
    controller.current_player_updates_queue.get_nowait()
    sleep_calls.clear()

    # Simulate a game ending
    controller.game_ended_event.set()

    # Process should detect unchanged stats, retry, and fail
    thread.process_updates()

    # Should have: sleep(5), detect stale (wins unchanged), sleep(65), then 60 retries
    assert sleep_calls == [5, 65] + [1] * 60

    # Only main should have been queued (the retry timed out)
    assert_controllers_equal(
        controller,
        create_controller(
            state=create_state(
                own_username="Main",
            ),
            current_player_updates=(main,),
        ),
        ignore_player_cache=True,
    )
