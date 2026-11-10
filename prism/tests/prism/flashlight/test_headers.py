from prism import VERSION_STRING
from prism.flashlight.headers import make_flashlight_client_headers


def test_make_flashlight_client_headers() -> None:
    assert make_flashlight_client_headers() == {
        "X-Client-Type": "prism",
        "X-Client-Version": VERSION_STRING,
    }


def test_make_flashlight_client_headers_returns_fresh_dict() -> None:
    # Callers merge and mutate the result, so it must not share state
    first = make_flashlight_client_headers()
    first["X-User-Id"] = "mutated"
    assert "X-User-Id" not in make_flashlight_client_headers()
