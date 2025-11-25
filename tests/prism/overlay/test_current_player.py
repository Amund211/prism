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
    controller.update_presence_event.set()

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
    assert not controller.update_presence_event.is_set()
    # Assert sleep was called with duration 5 (wait for Hypixel API update)
    # Player is already in cache from the sleep(5), so no additional sleep(1) needed
    assert sleep_calls == [5]


def test_username_is_none() -> None:
    """Test that processing stops early when username is None"""
    controller = create_controller(
        state=create_state(
            own_username=None,  # No username set
        ),
    )

    sleep_calls: list[float] = []

    def sleep(duration: float) -> None:
        sleep_calls.append(duration)

    thread = CurrentPlayerThread(controller=controller, sleep=sleep, timeout=0)

    # Process should do nothing when username is None
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

    # No sleep should have been called
    assert sleep_calls == []


def test_username_change_to_none() -> None:
    """Test that username change from a value to None is handled"""
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

    thread = CurrentPlayerThread(controller=controller, sleep=sleep, timeout=0)

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

    # No sleep should be called when username changes to None
    assert sleep_calls == []


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
    controller.update_presence_event.set()

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
    controller.update_presence_event.set()

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
    controller.update_presence_event.set()

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
            current_player_updates=(main,),
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
    controller.update_presence_event.set()

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
