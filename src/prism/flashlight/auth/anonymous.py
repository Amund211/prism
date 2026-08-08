import logging

import requests

from prism.flashlight.auth.endpoints import anonymous_login, request_challenge
from prism.flashlight.auth.proof_of_work import solve_challenge
from prism.flashlight.auth.session import Session

logger = logging.getLogger(__name__)


class AnonymousLogin:
    """
    The anonymous tier's `LoginMethod`: get a challenge, solve it, log in

    Anonymous identity costs one round trip and no user interaction, so it is
    what the overlay uses on first launch and by default. The proof-of-work is
    what prices minting identities at all; the server picks the difficulty and
    we just do the work.
    """

    tier = "anonymous"

    def __init__(
        self,
        *,
        requests_session: requests.Session,
        user_id: str,
    ) -> None:
        self._requests_session = requests_session

        # Read once, here, and used for both calls of the handshake. Flashlight
        # compares the userId sent to /challenge with the one sent to /login byte
        # for byte, so reading it from settings twice would risk a 403 that no
        # retry can fix.
        self._user_id = user_id

    def log_in(self) -> Session:  # pragma: nocover
        challenge = request_challenge(
            requests_session=self._requests_session, user_id=self._user_id
        )
        solution = solve_challenge(challenge)
        return anonymous_login(
            requests_session=self._requests_session,
            user_id=self._user_id,
            challenge=challenge.challenge,
            solution=solution,
        )
