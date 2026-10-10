import os
from collections.abc import Callable
from pathlib import Path

import pytest

from prism.flashlight.auth.credential_store import (
    CREDENTIAL_FILENAME,
    CredentialStore,
    StoredCredential,
)
from prism.flashlight.auth.errors import AuthError, CredentialRejectedError
from prism.flashlight.auth.microsoft import MicrosoftRecover
from prism.flashlight.auth.session import MicrosoftGrant
from tests.prism.auth_utils import make_session

OLD = StoredCredential(credential="O" * 43, uuid="a937646b-f115-44c3-8dbf-9ae4a65669a0")
ROTATED = "R" * 43
ROTATED_AGAIN = "S" * 43


def make_grant(credential: str = ROTATED) -> MicrosoftGrant:
    return MicrosoftGrant(
        session=make_session(tier="microsoft"), credential=credential, uuid=OLD.uuid
    )


class FakeRecover:
    def __init__(self, results: list[MicrosoftGrant | Exception]) -> None:
        self.results = results
        self.credentials: list[str] = []
        self.on_call: Callable[[], None] | None = None

    def __call__(self, credential: str) -> MicrosoftGrant:
        self.credentials.append(credential)
        if self.on_call is not None:
            self.on_call()
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def make_recover(
    tmp_path: Path, *results: MicrosoftGrant | Exception
) -> tuple[MicrosoftRecover, CredentialStore, FakeRecover]:
    store = CredentialStore(tmp_path / CREDENTIAL_FILENAME)
    store.write(OLD)
    fake = FakeRecover(list(results))
    return MicrosoftRecover(store=store, recover=fake, stored=OLD), store, fake


def fail_os_replace(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_replace(src: object, dst: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", fail_replace)


def test_log_in_persists_the_rotated_credential_before_returning(
    tmp_path: Path,
) -> None:
    grant = make_grant()
    login, store, fake = make_recover(tmp_path, grant)

    assert login.tier == "microsoft"
    assert login.uuid == OLD.uuid
    assert login.log_in() is grant.session

    assert fake.credentials == [OLD.credential]
    assert store.read() == StoredCredential(credential=ROTATED, uuid=OLD.uuid)


def test_log_in_recovers_with_the_latest_credential(tmp_path: Path) -> None:
    login, store, fake = make_recover(
        tmp_path, make_grant(ROTATED), make_grant(ROTATED_AGAIN)
    )

    login.log_in()
    login.log_in()

    assert fake.credentials == [OLD.credential, ROTATED]
    assert store.read() == StoredCredential(credential=ROTATED_AGAIN, uuid=OLD.uuid)


def test_log_in_deletes_a_rejected_credential(tmp_path: Path) -> None:
    login, store, _ = make_recover(tmp_path, CredentialRejectedError("401"))

    with pytest.raises(CredentialRejectedError):
        login.log_in()

    assert store.read() is None


def test_log_in_keeps_the_credential_on_a_transient_failure(tmp_path: Path) -> None:
    login, store, _ = make_recover(tmp_path, AuthError("status code 503"))

    with pytest.raises(AuthError) as e:
        login.log_in()

    assert not isinstance(e.value, CredentialRejectedError)
    assert store.read() == OLD


def test_log_in_keeps_the_successor_when_it_cannot_persist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    No session is committed until the successor is on disk

    The successor stays in memory, so the retry works however long the backoff
    is, even after the credential we sent has gone stale.
    """
    login, store, fake = make_recover(
        tmp_path, make_grant(ROTATED), make_grant(ROTATED_AGAIN)
    )
    fail_os_replace(monkeypatch)

    with pytest.raises(AuthError) as e:
        login.log_in()

    monkeypatch.undo()
    assert not isinstance(e.value, CredentialRejectedError)
    assert store.read() == OLD

    login.log_in()

    assert fake.credentials == [OLD.credential, ROTATED]
    assert store.read() == StoredCredential(credential=ROTATED_AGAIN, uuid=OLD.uuid)


def test_log_in_discards_what_it_last_persisted_when_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    login, store, _ = make_recover(
        tmp_path, make_grant(ROTATED), CredentialRejectedError("401")
    )
    fail_os_replace(monkeypatch)
    with pytest.raises(AuthError):
        login.log_in()
    monkeypatch.undo()

    with pytest.raises(CredentialRejectedError):
        login.log_in()

    assert store.read() is None


def test_log_in_keeps_a_credential_stored_during_the_recover(tmp_path: Path) -> None:
    """
    A sign-in mid-recover must not be undone by our rotated credential

    Rejected, so a file changed by hand drops this run to anonymous and is
    kept for the next start.
    """
    newer = StoredCredential(
        credential="N" * 43, uuid="0e7b5d9b-1c2a-4a3b-9c4d-5e6f7a8b9c0d"
    )
    login, store, fake = make_recover(tmp_path, make_grant())
    fake.on_call = lambda: store.write(newer)

    with pytest.raises(CredentialRejectedError):
        login.log_in()

    assert store.read() == newer
    assert login.uuid == OLD.uuid


def test_log_in_does_not_undo_a_sign_out_during_the_recover(tmp_path: Path) -> None:
    login, store, fake = make_recover(tmp_path, make_grant())
    fake.on_call = store.delete

    with pytest.raises(CredentialRejectedError):
        login.log_in()

    assert store.read() is None


def test_log_in_retries_when_the_store_cannot_be_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A locked file is not a signed-out user"""
    login, store, _ = make_recover(tmp_path, make_grant())

    def fail_read() -> StoredCredential | None:
        raise PermissionError("locked by antivirus")

    monkeypatch.setattr(store, "_read", fail_read)

    with pytest.raises(AuthError) as e:
        login.log_in()

    assert not isinstance(e.value, CredentialRejectedError)
