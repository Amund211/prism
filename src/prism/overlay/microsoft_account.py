import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from prism.flashlight.auth.credential_store import CredentialStore
from prism.flashlight.auth.errors import AuthError
from prism.flashlight.auth.manager import AuthManager
from prism.flashlight.auth.signin import SignInStatus

logger = logging.getLogger(__name__)

# NOTE: Never log the credential or the start url

MANAGE_SIGNINS_URL = "https://prismoverlay.com/settings"

WAITING_STATUS = "Waiting for browser…"
FINISHING_STATUS = "Finishing sign-in…"
SIGNING_OUT_STATUS = "Signing out…"
SIGN_OUT_FAILED_MESSAGE = "Could not sign out. Try again."

# Deletes every credential of the credential's identity. Raises AuthError.
Logout = Callable[[str], None]


class SignInFlow(Protocol):  # pragma: nocover
    @property
    def running(self) -> bool: ...

    @property
    def status(self) -> SignInStatus: ...

    def start(self) -> bool: ...

    def cancel(self) -> None: ...


class SignOutTarget(Protocol):  # pragma: nocover
    def sign_out_to_anonymous(self) -> None: ...


def sign_out_everywhere(
    *, auth: SignOutTarget, store: CredentialStore, logout: Logout
) -> None:
    """
    Delete the account's credentials on flashlight, then locally

    Raises AuthError or OSError, and then keeps everything, for a retry.
    """
    stored = store.read()
    if stored is not None:
        logout(stored.credential)
        store.delete()
    auth.sign_out_to_anonymous()


@dataclass(frozen=True, slots=True)
class AccountView:
    """What the settings page shows for the Microsoft account"""

    signed_in: bool
    # The username, or the uuid until (or if) it is resolved
    name: str | None
    status: str | None
    message: str | None
    start_url: str | None
    can_sign_in: bool
    can_cancel: bool
    can_sign_out: bool

    def __repr__(self) -> str:
        # Keeps the start url out of logs
        return f"AccountView(signed_in={self.signed_in}, status={self.status!r})"


class MicrosoftAccount:
    """
    The Microsoft account section's state and actions

    The tkinter thread calls everything here. Network work runs on threads of
    its own.
    """

    def __init__(
        self,
        *,
        auth: AuthManager,
        signin: SignInFlow,
        store: CredentialStore,
        logout: Logout,
        get_username: Callable[[str], str],
    ) -> None:
        """`get_username` returns the username for a dashed uuid, or raises"""
        self._auth = auth
        self._signin = signin
        self._store = store
        self._logout = logout
        self._get_username = get_username

        self._lock = threading.Lock()
        # Guarded by self._lock
        self._signing_out = False
        self._sign_out_error: str | None = None
        self._names: dict[str, str] = {}
        self._resolving: set[str] = set()
        self._failed: set[str] = set()
        self._dismissed_status: SignInStatus | None = None

    def view(self) -> AccountView:
        uuid = self._auth.signed_in_uuid
        status = self._signin.status
        signin_running = self._signin.running

        with self._lock:
            signing_out = self._signing_out
            sign_out_error = self._sign_out_error
            dismissed = status is self._dismissed_status

        if uuid is not None:
            return AccountView(
                signed_in=True,
                name=self._name(uuid),
                status=SIGNING_OUT_STATUS if signing_out else None,
                message=sign_out_error,
                start_url=None,
                can_sign_in=False,
                can_cancel=False,
                can_sign_out=not signing_out and not signin_running,
            )

        waiting = status.state == "waiting_for_browser"
        status_text = None
        if waiting:
            status_text = WAITING_STATUS
        elif status.state == "exchanging":
            status_text = FINISHING_STATUS

        return AccountView(
            signed_in=False,
            name=None,
            status=status_text,
            message=(
                status.message if status.state != "done" and not dismissed else None
            ),
            start_url=status.start_url if waiting else None,
            can_sign_in=not signin_running,
            can_cancel=waiting,
            can_sign_out=False,
        )

    def sign_in(self) -> None:
        self._signin.start()

    def cancel_sign_in(self) -> None:
        self._signin.cancel()

    def page_opened(self) -> None:
        """Clear old notices and errors, and retry failed name lookups"""
        self._auth.dismiss_signin_ended()
        status = self._signin.status
        with self._lock:
            self._sign_out_error = None
            self._failed.clear()
            if status.state == "failed":
                self._dismissed_status = status

    def sign_out(self) -> bool:
        """Start "Sign out everywhere". Return False if it cannot run now."""
        if self._signin.running:
            return False
        with self._lock:
            if self._signing_out:
                return False
            self._signing_out = True
            self._sign_out_error = None

        threading.Thread(
            target=self._sign_out, daemon=True, name="prism-ms-signout"
        ).start()
        return True

    def _sign_out(self) -> None:
        error = None
        try:
            sign_out_everywhere(auth=self._auth, store=self._store, logout=self._logout)
        except (AuthError, OSError) as e:
            logger.warning("Failed signing out of Microsoft", exc_info=e)
            error = SIGN_OUT_FAILED_MESSAGE
        else:
            logger.info("Signed out of Microsoft everywhere")

        with self._lock:
            self._signing_out = False
            self._sign_out_error = error

    def _name(self, uuid: str) -> str:
        with self._lock:
            name = self._names.get(uuid)
            if name is not None:
                return name
            if uuid in self._resolving or uuid in self._failed:
                return uuid
            self._resolving.add(uuid)

        threading.Thread(
            target=self._resolve, args=(uuid,), daemon=True, name="prism-ms-name"
        ).start()
        return uuid

    def _resolve(self, uuid: str) -> None:
        try:
            name = self._get_username(uuid)
        except Exception:
            logger.exception("Failed resolving the signed-in username")
            name = None

        with self._lock:
            self._resolving.discard(uuid)
            if name is None:
                self._failed.add(uuid)
            else:
                self._names[uuid] = name
