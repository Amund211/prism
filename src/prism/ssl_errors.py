from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    import requests


def is_missing_local_issuer_error(e: "requests.exceptions.SSLError") -> bool:
    """Return True if the error is due to missing local issuer cert"""
    return "local issuer certificate" in str(e)
