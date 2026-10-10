import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from prism.errors import APIError
from prism.flashlight.auth.credential_store import CredentialStore, StoredCredential
from prism.flashlight.auth.errors import AuthError, CredentialRejectedError
from prism.flashlight.auth.manager import AuthManager
from prism.flashlight.auth.signin import SignInStatus
from prism.overlay.microsoft_account import (
    FINISHING_STATUS,
    SIGN_OUT_FAILED_MESSAGE,
    WAITING_STATUS,
    AccountView,
    MicrosoftAccount,
    sign_out_everywhere,
)
from tests.prism.auth_utils import (
    TEST_UUID,
    make_auth_manager,
    make_microsoft_auth_manager,
    make_session,
)

CREDENTIAL = "C" * 43
START_URL = "https://flashlight.example/v1/auth/microsoft/start?x"


def wait_for(predicate: Callable[[], bool]) -> None:
    deadline = time.monotonic() + 5
    while not predicate():
        assert time.monotonic() < deadline, "Timed out"
        time.sleep(0.001)


class FakeSignIn:
    def __init__(self) -> None:
        self.status = SignInStatus("idle")
        self.starts = 0
        self.cancels = 0

    @property
    def running(self) -> bool:
        return self.status.state in ("waiting_for_browser", "exchanging")

    def start(self) -> bool:
        self.starts += 1
        return True

    def cancel(self) -> None:
        self.cancels += 1


class Logout:
    def __init__(self, store: CredentialStore) -> None:
        self.store = store
        self.credentials: list[str] = []
        self.error: Exception | None = None
        self.release: threading.Event | None = None
        self.file_existed: list[bool] = []

    def __call__(self, credential: str) -> None:
        self.credentials.append(credential)
        self.file_existed.append(self.store.path.exists())
        if self.release is not None:
            assert self.release.wait(5)
        if self.error is not None:
            raise self.error


class Usernames:
    def __init__(self, results: list[str | Exception]) -> None:
        self.results = results
        self.uuids: list[str] = []

    def __call__(self, uuid: str) -> str:
        self.uuids.append(uuid)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def make_store(tmp_path: Path, *, stored: bool = True) -> CredentialStore:
    store = CredentialStore(tmp_path / "microsoft_auth.json")
    if stored:
        store.write(StoredCredential(credential=CREDENTIAL, uuid=TEST_UUID))
    return store


def make_signed_in_manager() -> AuthManager:
    manager, _, _, _ = make_microsoft_auth_manager(
        microsoft_results=[make_session(tier="microsoft")]
    )
    manager.reconcile()
    return manager


def make_anonymous_manager() -> AuthManager:
    manager, _, _ = make_auth_manager(login_results=[make_session()])
    manager.reconcile()
    return manager


def make_account(
    tmp_path: Path,
    *,
    auth: AuthManager,
    usernames: Usernames | None = None,
) -> tuple[MicrosoftAccount, FakeSignIn, Logout, CredentialStore]:
    store = make_store(tmp_path, stored=auth.tier == "microsoft")
    signin = FakeSignIn()
    logout = Logout(store)
    account = MicrosoftAccount(
        auth=auth,
        signin=signin,
        store=store,
        logout=logout,
        get_username=usernames or Usernames(["Leto"]),
    )
    return account, signin, logout, store


def test_sign_out_everywhere_logs_out_then_deletes_the_file(tmp_path: Path) -> None:
    auth = make_signed_in_manager()
    store = make_store(tmp_path)
    logout = Logout(store)

    sign_out_everywhere(auth=auth, store=store, logout=logout)

    assert logout.credentials == [CREDENTIAL]
    assert logout.file_existed == [True]
    assert not store.path.exists()
    assert auth.tier == "anonymous"
    assert auth.signed_in_uuid is None
    assert auth.wait_for_session(timeout=0) is None


@pytest.mark.parametrize("error", [AuthError("500"), CredentialRejectedError("x")])
def test_sign_out_everywhere_keeps_everything_when_logout_fails(
    tmp_path: Path, error: Exception
) -> None:
    auth = make_signed_in_manager()
    store = make_store(tmp_path)
    logout = Logout(store)
    logout.error = error

    with pytest.raises(AuthError):
        sign_out_everywhere(auth=auth, store=store, logout=logout)

    assert store.read() == StoredCredential(credential=CREDENTIAL, uuid=TEST_UUID)
    assert auth.tier == "microsoft"
    assert auth.wait_for_session(timeout=0) is not None


def test_sign_out_everywhere_keeps_everything_when_the_file_is_unreadable(
    tmp_path: Path,
) -> None:
    auth = make_signed_in_manager()
    store = CredentialStore(tmp_path)  # A directory: reading it raises
    logout = Logout(store)

    with pytest.raises(OSError):
        sign_out_everywhere(auth=auth, store=store, logout=logout)

    assert logout.credentials == []
    assert auth.tier == "microsoft"


def test_sign_out_everywhere_without_a_file_signs_out_locally(tmp_path: Path) -> None:
    auth = make_signed_in_manager()
    store = make_store(tmp_path, stored=False)
    logout = Logout(store)

    sign_out_everywhere(auth=auth, store=store, logout=logout)

    assert logout.credentials == []
    assert auth.tier == "anonymous"


def test_anonymous_view(tmp_path: Path) -> None:
    account, _, _, _ = make_account(tmp_path, auth=make_anonymous_manager())

    assert account.view() == AccountView(
        signed_in=False,
        name=None,
        status=None,
        message=None,
        start_url=None,
        can_sign_in=True,
        can_cancel=False,
        can_sign_out=False,
    )


def test_sign_in_and_cancel_go_to_the_flow(tmp_path: Path) -> None:
    account, signin, _, _ = make_account(tmp_path, auth=make_anonymous_manager())

    account.sign_in()
    account.cancel_sign_in()

    assert (signin.starts, signin.cancels) == (1, 1)


@pytest.mark.parametrize("message", [None, "Could not open the browser."])
def test_waiting_view_always_shows_the_link(tmp_path: Path, message: str) -> None:
    account, signin, _, _ = make_account(tmp_path, auth=make_anonymous_manager())
    signin.status = SignInStatus("waiting_for_browser", message, start_url=START_URL)

    view = account.view()

    assert view.status == WAITING_STATUS
    assert view.message == message
    assert view.start_url == START_URL
    assert view.can_cancel
    assert not view.can_sign_in


def test_view_repr_leaves_out_the_start_url(tmp_path: Path) -> None:
    account, signin, _, _ = make_account(tmp_path, auth=make_anonymous_manager())
    signin.status = SignInStatus("waiting_for_browser", start_url=START_URL)

    assert START_URL not in repr(account.view())


def test_exchanging_view(tmp_path: Path) -> None:
    account, signin, _, _ = make_account(tmp_path, auth=make_anonymous_manager())
    signin.status = SignInStatus("exchanging")

    view = account.view()

    assert view.status == FINISHING_STATUS
    assert view.start_url is None
    assert not view.can_cancel
    assert not view.can_sign_in


def test_failed_view_shows_the_message_and_allows_a_retry(tmp_path: Path) -> None:
    account, signin, _, _ = make_account(tmp_path, auth=make_anonymous_manager())
    signin.status = SignInStatus("failed", "Sign-in expired. Try again.")

    view = account.view()

    assert view.status is None
    assert view.message == "Sign-in expired. Try again."
    assert view.can_sign_in


def test_signed_in_view_resolves_the_name_once(tmp_path: Path) -> None:
    usernames = Usernames(["Leto"])
    account, _, _, _ = make_account(
        tmp_path, auth=make_signed_in_manager(), usernames=usernames
    )

    first = account.view()
    assert first.signed_in
    assert first.name in (TEST_UUID, "Leto")
    assert first.can_sign_out
    assert not first.can_sign_in

    wait_for(lambda: account.view().name == "Leto")
    account.view()

    assert usernames.uuids == [TEST_UUID]


def test_a_failed_name_lookup_falls_back_to_the_uuid_until_the_page_opens(
    tmp_path: Path,
) -> None:
    usernames = Usernames([APIError("down"), "Leto"])
    account, _, _, _ = make_account(
        tmp_path, auth=make_signed_in_manager(), usernames=usernames
    )

    account.view()
    wait_for(lambda: TEST_UUID in account._failed)
    assert account.view().name == TEST_UUID
    assert len(usernames.uuids) == 1

    account.page_opened()

    wait_for(lambda: account.view().name == "Leto")
    assert len(usernames.uuids) == 2


def test_page_opened_while_a_lookup_runs_does_not_start_another(
    tmp_path: Path,
) -> None:
    release = threading.Event()

    def get_username(uuid: str) -> str:
        assert release.wait(5)
        raise APIError("down")

    store = make_store(tmp_path)
    account = MicrosoftAccount(
        auth=make_signed_in_manager(),
        signin=FakeSignIn(),
        store=store,
        logout=Logout(store),
        get_username=get_username,
    )

    account.view()
    account.page_opened()
    account.view()
    assert TEST_UUID in account._resolving

    release.set()

    # The failure is kept until the next page open, even though one ran during it
    wait_for(lambda: TEST_UUID in account._failed)
    assert account.view().name == TEST_UUID


def test_page_opened_clears_an_old_sign_in_failure(tmp_path: Path) -> None:
    account, signin, _, _ = make_account(tmp_path, auth=make_anonymous_manager())
    signin.status = SignInStatus("failed", "Sign-in expired. Try again.")

    account.page_opened()

    assert account.view().message is None

    # A new failure shows again
    signin.status = SignInStatus("failed", "Sign-in expired. Try again.")
    assert account.view().message == "Sign-in expired. Try again."


def test_page_opened_clears_an_old_sign_out_error(tmp_path: Path) -> None:
    account, _, logout, _ = make_account(tmp_path, auth=make_signed_in_manager())
    logout.error = AuthError("Logout failed, status code 500")
    assert account.sign_out()
    wait_for(lambda: account.view().message == SIGN_OUT_FAILED_MESSAGE)

    account.page_opened()

    assert account.view().message is None


def test_page_opened_dismisses_signin_ended(tmp_path: Path) -> None:
    auth, _, _, _ = make_microsoft_auth_manager(
        microsoft_results=[CredentialRejectedError("401")],
        anonymous_results=[make_session()],
    )
    auth.reconcile()
    account, _, _, _ = make_account(tmp_path, auth=auth)
    assert auth.microsoft_signin_ended

    account.page_opened()

    assert not auth.microsoft_signin_ended


def test_sign_out_is_refused_while_a_sign_in_runs(tmp_path: Path) -> None:
    account, signin, logout, _ = make_account(tmp_path, auth=make_signed_in_manager())
    signin.status = SignInStatus("exchanging")

    assert not account.view().can_sign_out
    assert not account.sign_out()
    assert logout.credentials == []


def test_sign_out_runs_in_the_background(tmp_path: Path) -> None:
    auth = make_signed_in_manager()
    account, _, logout, store = make_account(tmp_path, auth=auth)
    logout.release = threading.Event()

    assert account.sign_out()

    wait_for(lambda: len(logout.credentials) == 1)
    view = account.view()
    assert view.status == "Signing out…"
    assert not view.can_sign_out
    # A second click while one runs is refused
    assert not account.sign_out()

    logout.release.set()

    wait_for(lambda: not account.view().signed_in)
    assert account.view().can_sign_in
    assert not store.path.exists()
    assert logout.credentials == [CREDENTIAL]


def test_a_failed_sign_out_shows_an_error_and_keeps_everything(
    tmp_path: Path,
) -> None:
    auth = make_signed_in_manager()
    account, _, logout, store = make_account(tmp_path, auth=auth)
    logout.error = AuthError("Logout failed, status code 500")

    assert account.sign_out()

    wait_for(lambda: account.view().message == SIGN_OUT_FAILED_MESSAGE)
    view = account.view()
    assert view.signed_in
    assert view.can_sign_out
    assert view.status is None
    assert store.path.exists()

    # A retry clears the error
    logout.error = None
    assert account.sign_out()
    wait_for(lambda: not account.view().signed_in)
    assert account.view().message is None
