import pytest
from requests.exceptions import SSLError

from prism.ssl_errors import is_missing_local_issuer_error


@pytest.mark.parametrize(
    "error, is_missing_local_issuer",
    (
        (
            SSLError(
                """MaxRetryError("HTTPSConnectionPool(host='localhost', port=12345): Max retries exceeded with url: / (Caused by SSLError(SSLCertVerificationError(1, '[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1000)')))")"""  # noqa: E501
            ),
            True,
        ),
        (
            SSLError("Oopsie doopsie, something went wrong"),
            False,
        ),
    ),
)
def test_is_missing_local_issuer_error(
    error: SSLError, is_missing_local_issuer: bool
) -> None:
    assert is_missing_local_issuer_error(error) == is_missing_local_issuer
