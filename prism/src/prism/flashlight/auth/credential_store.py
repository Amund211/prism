import json
import logging
import os
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from prism.flashlight.auth.validation import CREDENTIAL_RE, DASHED_UUID_RE

logger = logging.getLogger(__name__)

CREDENTIAL_FILENAME = "microsoft_auth.json"

FORMAT_VERSION = 1

# NOTE: The credential is a long-lived secret. Never log it or the file content.

# Shared by all stores: the auth and sign-in threads both read-modify-write
_LOCK = threading.Lock()


@dataclass(frozen=True, slots=True)
class StoredCredential:
    """A flashlight Microsoft-tier credential and the dashed uuid it signs in as"""

    credential: str
    uuid: str


def _parse(content: str) -> StoredCredential | None:
    try:
        data = json.loads(content)
    except ValueError:
        return None

    if not isinstance(data, dict) or data.get("v") != FORMAT_VERSION:
        return None

    credential, uuid = data.get("credential"), data.get("uuid")
    if not isinstance(credential, str) or not CREDENTIAL_RE.match(credential):
        return None
    if not isinstance(uuid, str) or not DASHED_UUID_RE.match(uuid):
        return None

    return StoredCredential(credential=credential, uuid=uuid)


class CredentialStore:
    """
    The Microsoft-tier credential file

    Writes are atomic, so a crash at any point leaves either the old or the new
    credential on disk.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> StoredCredential | None:
        """
        Return the stored credential, or None if there is none

        A corrupt file is deleted, so it can never wedge startup. Raises OSError
        when the file exists but cannot be read.
        """
        with _LOCK:
            return self._read()

    def write(self, stored: StoredCredential) -> None:
        """Atomically replace the stored credential. Raises OSError."""
        with _LOCK:
            self._write(stored)

    def replace(self, expected: str, stored: StoredCredential) -> bool:
        """
        Write `stored`, but only over the credential `expected`

        Return False, and write nothing, if the file holds another credential or
        none. Raises OSError.
        """
        with _LOCK:
            current = self._read()
            if current is None or current.credential != expected:
                return False
            self._write(stored)
            return True

    def delete(self) -> None:
        """Delete the stored credential, if any"""
        with _LOCK:
            self._delete()

    def discard(self, credential: str) -> None:
        """Delete the stored credential, but only if it is `credential`"""
        with _LOCK:
            try:
                stored = self._read()
            except OSError:
                logger.exception("Failed reading the Microsoft credential file")
                return
            if stored is not None and stored.credential == credential:
                self._delete()

    def _read(self) -> StoredCredential | None:
        try:
            content = self.path.read_text("utf-8")
        except FileNotFoundError:
            return None
        except UnicodeDecodeError:
            content = ""

        stored = _parse(content)
        if stored is None:
            logger.warning("Deleting an invalid Microsoft credential file")
            self._delete()
        return stored

    def _write(self, stored: StoredCredential) -> None:
        content = json.dumps(
            {"v": FORMAT_VERSION, "credential": stored.credential, "uuid": stored.uuid}
        )
        fd, temp_name = tempfile.mkstemp(
            dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            # Explicit, so the mode does not depend on mkstemp. No-op on Windows.
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, self.path)
        except BaseException:
            try:
                os.unlink(temp_name)
            except OSError:  # pragma: nocover
                pass
            raise

    def _delete(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError:  # pragma: nocover
            logger.exception("Failed deleting the Microsoft credential file")
