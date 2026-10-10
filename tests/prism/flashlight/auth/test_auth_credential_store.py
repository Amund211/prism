import json
import os
import stat
import sys
from pathlib import Path

import pytest

from prism.flashlight.auth.credential_store import (
    CREDENTIAL_FILENAME,
    CredentialStore,
    StoredCredential,
)

CREDENTIAL = "A" * 42 + "_"
OTHER_CREDENTIAL = "B" * 42 + "-"
UUID = "a937646b-f115-44c3-8dbf-9ae4a65669a0"


def make_store(tmp_path: Path) -> CredentialStore:
    return CredentialStore(tmp_path / CREDENTIAL_FILENAME)


def test_read_missing_file(tmp_path: Path) -> None:
    assert make_store(tmp_path).read() is None


def test_round_trip(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    stored = StoredCredential(credential=CREDENTIAL, uuid=UUID)

    store.write(stored)

    assert store.read() == stored
    assert json.loads(store.path.read_text("utf-8")) == {
        "v": 1,
        "credential": CREDENTIAL,
        "uuid": UUID,
    }


def test_write_replaces(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.write(StoredCredential(credential=CREDENTIAL, uuid=UUID))

    store.write(StoredCredential(credential=OTHER_CREDENTIAL, uuid=UUID))

    assert store.read() == StoredCredential(credential=OTHER_CREDENTIAL, uuid=UUID)


def test_write_leaves_no_temp_file(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    store.write(StoredCredential(credential=CREDENTIAL, uuid=UUID))
    store.write(StoredCredential(credential=OTHER_CREDENTIAL, uuid=UUID))

    assert os.listdir(tmp_path) == [CREDENTIAL_FILENAME]


def test_failed_write_leaves_no_temp_file_and_keeps_the_old_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = make_store(tmp_path)
    old = StoredCredential(credential=CREDENTIAL, uuid=UUID)
    store.write(old)

    def fail_replace(src: object, dst: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(OSError):
        store.write(StoredCredential(credential=OTHER_CREDENTIAL, uuid=UUID))

    monkeypatch.undo()
    assert os.listdir(tmp_path) == [CREDENTIAL_FILENAME]
    assert store.read() == old


@pytest.mark.skipif(sys.platform == "win32", reason="chmod is a no-op on Windows")
def test_write_is_owner_only(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    store.write(StoredCredential(credential=CREDENTIAL, uuid=UUID))

    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600


def test_delete(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.write(StoredCredential(credential=CREDENTIAL, uuid=UUID))

    store.delete()
    store.delete()  # Missing is fine

    assert store.read() is None


def test_discard_deletes_a_matching_credential(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.write(StoredCredential(credential=CREDENTIAL, uuid=UUID))

    store.discard(CREDENTIAL)

    assert store.read() is None


def test_discard_keeps_a_newer_credential(tmp_path: Path) -> None:
    """The sign-in thread may have stored a new one since we read it"""
    store = make_store(tmp_path)
    newer = StoredCredential(credential=OTHER_CREDENTIAL, uuid=UUID)
    store.write(newer)

    store.discard(CREDENTIAL)

    assert store.read() == newer


def test_discard_missing_file(tmp_path: Path) -> None:
    store = make_store(tmp_path)

    store.discard(CREDENTIAL)

    assert store.read() is None


def test_discard_unreadable_file(tmp_path: Path) -> None:
    """Best effort: the next recover is rejected again and retries the discard"""
    CredentialStore(tmp_path).discard(CREDENTIAL)

    assert tmp_path.exists()


def test_replace_writes_over_the_expected_credential(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.write(StoredCredential(credential=CREDENTIAL, uuid=UUID))
    rotated = StoredCredential(credential=OTHER_CREDENTIAL, uuid=UUID)

    assert store.replace(CREDENTIAL, rotated)

    assert store.read() == rotated


def test_replace_keeps_a_newer_credential(tmp_path: Path) -> None:
    """A sign-in stored a new credential while our recover ran"""
    store = make_store(tmp_path)
    newer = StoredCredential(credential=OTHER_CREDENTIAL, uuid=UUID)
    store.write(newer)

    assert not store.replace(
        CREDENTIAL, StoredCredential(credential="R" * 43, uuid=UUID)
    )

    assert store.read() == newer


def test_replace_does_not_bring_back_a_deleted_file(tmp_path: Path) -> None:
    """A sign-out deleted the credential while our recover ran"""
    store = make_store(tmp_path)

    assert not store.replace(
        CREDENTIAL, StoredCredential(credential="R" * 43, uuid=UUID)
    )

    assert store.read() is None


@pytest.mark.parametrize(
    "content",
    (
        "",
        "not json",
        "[]",
        json.dumps({"credential": CREDENTIAL, "uuid": UUID}),
        json.dumps({"v": 2, "credential": CREDENTIAL, "uuid": UUID}),
        json.dumps({"v": 1, "uuid": UUID}),
        json.dumps({"v": 1, "credential": CREDENTIAL}),
        json.dumps({"v": 1, "credential": "too short", "uuid": UUID}),
        json.dumps({"v": 1, "credential": "A" * 42 + "=", "uuid": UUID}),
        json.dumps({"v": 1, "credential": 1, "uuid": UUID}),
        json.dumps({"v": 1, "credential": CREDENTIAL, "uuid": UUID.replace("-", "")}),
        json.dumps({"v": 1, "credential": CREDENTIAL, "uuid": UUID.upper()}),
        json.dumps({"v": 1, "credential": CREDENTIAL, "uuid": None}),
    ),
)
def test_read_deletes_a_corrupt_file(tmp_path: Path, content: str) -> None:
    """A corrupt file must never wedge startup"""
    store = make_store(tmp_path)
    store.path.write_text(content, "utf-8")

    assert store.read() is None
    assert not store.path.exists()


def test_read_deletes_invalid_utf8(tmp_path: Path) -> None:
    store = make_store(tmp_path)
    store.path.write_bytes(b"\xff\xfe")

    assert store.read() is None
    assert not store.path.exists()


def test_read_unreadable_file(tmp_path: Path) -> None:
    """
    An I/O error is not a missing credential, and the file is kept

    On Windows, an antivirus can lock the file for a moment.
    """
    store = CredentialStore(tmp_path)  # A directory cannot be read as a file

    with pytest.raises(OSError):
        store.read()

    assert tmp_path.exists()
