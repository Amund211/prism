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

    main = make_player("player", "Main")

    def sleep(duration: float) -> None:
        assert duration == 1
        # We simulate the stats thread fetching the player data in the background by
        # populating the cache after one sleep
        controller.player_cache.set_cached_player(
            "Main", main, genus=controller.player_cache.current_genus
        )
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

    # TODO: assert sleep not called

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
            current_player_updates=(main,),
        ),
        ignore_player_cache=True,
    )
    # assert event cleared
