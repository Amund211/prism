import pytest

from prism.overlay.server import Server, ServerKind, classify_server, server_is_active


@pytest.mark.parametrize(
    "host, kind",
    (
        ("hypixel.net", "hypixel"),
        ("mc.hypixel.net", "hypixel"),
        ("stuck.hypixel.net", "hypixel"),
        ("bedwars.hypixel.net", "hypixel"),
        ("HYPIXEL.NET", "hypixel"),
        ("Mc.Hypixel.Net", "hypixel"),
        ("nothypixel.net", "other"),
        ("hypixel.net.evil.com", "other"),
        ("hypixel.com", "other"),
        ("bedwarspractice.club", "other"),
        ("eu.minemen.club", "other"),
        ("localhost", "local"),
        ("127.0.0.1", "local"),
        ("127.1.2.3", "local"),
        ("::1", "local"),
        ("10.0.0.1", "local"),
        ("172.16.0.1", "local"),
        ("172.31.255.255", "local"),
        ("192.168.0.102", "local"),
        ("1.2.3.4", "ip"),
        ("172.32.0.1", "ip"),
        ("2001:4860:4860::8888", "ip"),
    ),
)
def test_classify_server(host: str, kind: ServerKind) -> None:
    assert classify_server(host) == kind


@pytest.mark.parametrize(
    "server, active",
    (
        (None, True),
        (Server(host="mc.hypixel.net", kind="hypixel"), True),
        (Server(host="localhost", kind="local"), True),
        (Server(host="1.2.3.4", kind="ip"), True),
        (Server(host="bedwarspractice.club", kind="other"), False),
        (Server(host=None, kind="singleplayer"), False),
    ),
)
def test_server_is_active(server: Server | None, active: bool) -> None:
    assert server_is_active(server) == active


def test_server_from_host() -> None:
    assert Server.from_host("mc.hypixel.net") == Server(
        host="mc.hypixel.net", kind="hypixel"
    )
    assert Server.singleplayer() == Server(host=None, kind="singleplayer")
