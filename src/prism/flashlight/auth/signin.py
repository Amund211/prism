import base64
import hashlib
import logging
import secrets
import threading
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Literal, Protocol

from prism.flashlight.auth.credential_store import CredentialStore, StoredCredential
from prism.flashlight.auth.errors import AuthError, CredentialRejectedError
from prism.flashlight.auth.loopback import Callback, LoopbackListener
from prism.flashlight.auth.manager import MicrosoftLoginMethod
from prism.flashlight.auth.microsoft import MicrosoftRecover, Recover
from prism.flashlight.auth.session import MicrosoftGrant, Session
from prism.flashlight.url import FLASHLIGHT_API_URL

logger = logging.getLogger(__name__)

# NOTE: Never log the result token, the verifier, the credential or the start
#       url. The url's challenge and state are of no use alone, but keep it out.

# The lifetime of flashlight's flow cookie
SIGNIN_TIMEOUT_SECONDS = 600.0

EXPIRED_MESSAGE = "Sign-in expired. Try again."
FAILED_MESSAGE = "Sign-in failed. Try again later."
SAVE_FAILED_MESSAGE = "Could not save the sign-in. Try again."
BROWSER_FAILED_MESSAGE = "Could not open the browser. Copy the link into your browser."
# Shown before the exchange, so it must not claim the sign-in succeeded
CALLBACK_RECEIVED_MESSAGE = (
    "You can close this tab and return to Prism to finish signing in."
)

_ERROR_MESSAGES = {
    "client_not_approved": "Microsoft sign-in is not available yet.",
    "no_game": "This Microsoft account does not own Minecraft Java Edition.",
    "no_profile": "This Microsoft account does not own Minecraft Java Edition.",
    "no_xbox_account": (
        "This Microsoft account has no Xbox profile. "
        "Sign in once at xbox.com, then try again."
    ),
    "child_account": "Xbox needs an adult to approve this account.",
    "adult_verification_required": "Xbox needs an adult to approve this account.",
    "xbox_unavailable_in_region": "Xbox Live is not available in your region.",
    "microsoft_error": "Sign-in was cancelled.",
    "flow_missing": EXPIRED_MESSAGE,
    "flow_invalid": EXPIRED_MESSAGE,
    "flow_expired": EXPIRED_MESSAGE,
    "state_mismatch": EXPIRED_MESSAGE,
    "code_rejected": EXPIRED_MESSAGE,
    "invalid_callback": EXPIRED_MESSAGE,
}


def error_message(code: str) -> str:
    """The user-facing message for a callback error code"""
    return _ERROR_MESSAGES.get(code, FAILED_MESSAGE)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def make_pkce() -> tuple[str, str]:
    """Return a new (verifier, challenge) pair"""
    verifier = _b64(secrets.token_bytes(32))
    challenge = _b64(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def _describe(callback: Callback) -> str:
    if callback.error is not None:
        return error_message(callback.error)
    return CALLBACK_RECEIVED_MESSAGE


SignInState = Literal["idle", "waiting_for_browser", "exchanging", "failed", "done"]


@dataclass(frozen=True, slots=True)
class SignInStatus:
    """
    Where the sign-in is, and a message for the user

    `start_url` is set while waiting for the browser, for the user to open by
    hand. Do not log it.
    """

    state: SignInState
    message: str | None = None
    start_url: str | None = field(default=None, repr=False)


class Exchange(Protocol):  # pragma: nocover
    def __call__(self, *, result: str, verifier: str) -> MicrosoftGrant:
        """Exchange the callback's result for a session. Raises AuthError."""


class Adopter(Protocol):  # pragma: nocover
    def adopt(self, session: Session, login_method: MicrosoftLoginMethod) -> None:
        """Switch to the signed-in account"""


class MicrosoftSignIn:
    """
    The interactive Microsoft sign-in, on its own thread

    Opens flashlight's start url in the browser and waits for the callback on a
    loopback listener. The credential is stored before the auth manager adopts
    the session, so a crash never leaves a session we cannot recover.
    """

    def __init__(
        self,
        *,
        auth: Adopter,
        store: CredentialStore,
        exchange: Exchange,
        recover: Recover,
        open_url: Callable[[str], bool],
        timeout_seconds: float = SIGNIN_TIMEOUT_SECONDS,
    ) -> None:
        """
        `open_url` returns False, or raises, when no browser opened. The flow
        then keeps waiting, and `status.start_url` is for the user to open by
        hand. `webbrowser.open` fits, and unlike the overlay's `open_url`
        helper it does not log the url.
        """
        self._auth = auth
        self._store = store
        self._exchange = exchange
        self._recover = recover
        self._open_url = open_url
        self._timeout_seconds = timeout_seconds

        self._lock = threading.Lock()
        # Guarded by self._lock
        self._status = SignInStatus("idle")
        self._listener: LoopbackListener | None = None
        self._cancelled = False

    @property
    def status(self) -> SignInStatus:
        with self._lock:
            return self._status

    @property
    def running(self) -> bool:
        """True while a sign-in is in progress"""
        with self._lock:
            return self._status.state in ("waiting_for_browser", "exchanging")

    def start(self) -> bool:
        """Start a sign-in. Return False if one is already running."""
        with self._lock:
            if self._status.state in ("waiting_for_browser", "exchanging"):
                return False
            self._status = SignInStatus("waiting_for_browser")
            self._cancelled = False

        threading.Thread(target=self._run, daemon=True, name="prism-ms-signin").start()
        return True

    def cancel(self) -> None:
        """Stop waiting for the browser. An exchange in flight is not cancelled."""
        with self._lock:
            if self._status.state != "waiting_for_browser":
                return
            self._cancelled = True
            listener = self._listener

        if listener is not None:
            listener.cancel()

    def _run(self) -> None:
        try:
            status = self._sign_in()
        except Exception:
            logger.exception("Unexpected error during Microsoft sign-in")
            status = SignInStatus("failed", FAILED_MESSAGE)

        logger.info(f"Microsoft sign-in finished: {status.state}")
        with self._lock:
            self._listener = None
            self._status = status

    def _open_browser(self, url: str) -> bool:
        try:
            opened = self._open_url(url)
        except Exception as e:
            # Not logged with the exception: its message may hold the url
            logger.warning(f"Failed opening the browser: {type(e).__name__}")
            return False

        if not opened:
            logger.warning("Failed opening the browser")
        return opened

    def _sign_in(self) -> SignInStatus:
        verifier, challenge = make_pkce()
        state = secrets.token_urlsafe(32)

        with LoopbackListener(state=state, describe=_describe) as listener:
            with self._lock:
                self._listener = listener
                if self._cancelled:
                    return SignInStatus("idle")

            query = urllib.parse.urlencode(
                {
                    "return": listener.callback_url,
                    "challenge": challenge,
                    "state": state,
                }
            )
            url = f"{FLASHLIGHT_API_URL}/v1/auth/microsoft/start?{query}"
            with self._lock:
                self._status = SignInStatus("waiting_for_browser", start_url=url)

            logger.info("Opening the browser for Microsoft sign-in")
            if not self._open_browser(url):
                with self._lock:
                    self._status = SignInStatus(
                        "waiting_for_browser", BROWSER_FAILED_MESSAGE, start_url=url
                    )

            callback = listener.wait(self._timeout_seconds)

        with self._lock:
            if self._cancelled:
                return SignInStatus("idle")
            if callback is not None and callback.error is None:
                self._status = SignInStatus("exchanging")

        if callback is None:
            logger.info("Timed out waiting for the Microsoft sign-in callback")
            return SignInStatus("failed", EXPIRED_MESSAGE)

        if callback.error is not None:
            # A machine code from flashlight, not a secret
            logger.info(f"Microsoft sign-in callback error {callback.error!r}")
            return SignInStatus("failed", error_message(callback.error))

        assert callback.result is not None
        return self._complete(callback.result, verifier)

    def _complete(self, result: str, verifier: str) -> SignInStatus:
        """exchange -> store -> adopt, in that order"""
        try:
            grant = self._exchange(result=result, verifier=verifier)
        except CredentialRejectedError:
            logger.info("Flashlight rejected the Microsoft sign-in result")
            return SignInStatus("failed", EXPIRED_MESSAGE)
        except AuthError as e:
            logger.warning("Microsoft sign-in exchange failed", exc_info=e)
            return SignInStatus("failed", FAILED_MESSAGE)

        stored = StoredCredential(credential=grant.credential, uuid=grant.uuid)
        try:
            self._store.write(stored)
        except OSError as e:
            # Not adopted: a session we could not recover after a restart
            logger.warning("Failed storing the Microsoft credential", exc_info=e)
            return SignInStatus("failed", SAVE_FAILED_MESSAGE)

        self._auth.adopt(
            grant.session,
            MicrosoftRecover(store=self._store, recover=self._recover, stored=stored),
        )
        return SignInStatus("done")
