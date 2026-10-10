import logging
from collections.abc import Callable

from prism.flashlight.auth.credential_store import CredentialStore, StoredCredential
from prism.flashlight.auth.errors import AuthError, CredentialRejectedError
from prism.flashlight.auth.session import MicrosoftGrant, Session

logger = logging.getLogger(__name__)

# Trades a credential for a session and the credential's successor
Recover = Callable[[str], MicrosoftGrant]


class MicrosoftRecover:
    """
    The Microsoft tier's `LoginMethod`: recover with our latest credential

    Every recover rotates the credential, and the old one goes stale a minute
    later. The latest one is kept in memory; the file only carries it to the
    next start. So the successor is on disk before the session is handed out,
    and a failed write loses nothing.
    """

    tier = "microsoft"

    def __init__(
        self, *, store: CredentialStore, recover: Recover, stored: StoredCredential
    ) -> None:
        self._store = store
        self._recover = recover
        self._uuid = stored.uuid
        self._credential = stored.credential
        # What the file holds, unless someone else changed it
        self._persisted = stored.credential

    @property
    def uuid(self) -> str:
        """The dashed uuid this signs in as"""
        return self._uuid

    def log_in(self) -> Session:
        try:
            grant = self._recover(self._credential)
        except CredentialRejectedError:
            self._store.discard(self._persisted)
            raise

        self._credential = grant.credential

        try:
            replaced = self._store.replace(
                self._persisted,
                StoredCredential(credential=grant.credential, uuid=self._uuid),
            )
        except OSError as e:
            raise AuthError("Failed storing the rotated Microsoft credential") from e

        if not replaced:
            # A sign-in, a sign-out or a hand edit changed the file. It wins.
            raise CredentialRejectedError("The Microsoft credential file changed")

        self._persisted = grant.credential
        return grant.session
