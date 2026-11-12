import json
from pathlib import Path

import pytest

from prism.overlay.tabshot.game_info import (
    collect_game_info,
    detect_launcher,
    get_active_logfile,
    parse_cmdline,
    parse_log_head,
    parse_options,
    redact_cmdline,
    set_active_logfile,
)

HOME = "C:\\Users\\user"


@pytest.mark.parametrize(
    "logfile, launcher, profile, game_dir",
    (
        (
            f"{HOME}\\.lunarclient\\profiles\\1.8\\logs\\latest.log",
            "lunar",
            "1.8",
            f"{HOME}\\.lunarclient\\profiles\\1.8",
        ),
        (
            f"{HOME}\\.lunarclient\\offline\\multiver\\logs\\latest.log",
            "lunar",
            "offline/multiver",
            f"{HOME}\\AppData\\Roaming\\.minecraft",
        ),
        (
            f"{HOME}\\AppData\\Roaming\\.minecraft\\logs\\blclient\\minecraft"
            "\\latest.log",
            "badlion",
            None,
            f"{HOME}\\AppData\\Roaming\\.minecraft",
        ),
        (
            f"{HOME}\\AppData\\Roaming\\PrismLauncher\\instances\\1.8.9\\.minecraft"
            "\\logs\\latest.log",
            "prismlauncher",
            "1.8.9",
            f"{HOME}\\AppData\\Roaming\\PrismLauncher\\instances\\1.8.9\\.minecraft",
        ),
        (
            f"{HOME}\\AppData\\Roaming\\.minecraft\\logs\\fml-client-latest.log",
            "forge",
            None,
            f"{HOME}\\AppData\\Roaming\\.minecraft",
        ),
        (
            f"{HOME}\\AppData\\Roaming\\.minecraft\\logs\\latest.log",
            "minecraft_launcher",
            None,
            f"{HOME}\\AppData\\Roaming\\.minecraft",
        ),
        (
            "/home/a/.lunarclient/profiles/1.21/logs/latest.log",
            "lunar",
            "1.21",
            "/home/a/.lunarclient/profiles/1.21",
        ),
        ("/somewhere/odd.log", "unknown", None, None),
    ),
)
def test_detect_launcher(
    logfile: str, launcher: str, profile: str | None, game_dir: str | None
) -> None:
    result = detect_launcher(logfile)
    assert result["launcher"] == launcher
    assert result["profile"] == profile
    assert result["game_dir"] == game_dir


def test_detect_launcher_dirs() -> None:
    lunar = detect_launcher(f"{HOME}\\.lunarclient\\profiles\\1.8\\logs\\latest.log")
    assert lunar["launcher_dir"] == f"{HOME}\\.lunarclient"
    assert lunar["minecraft_dir"] == f"{HOME}\\AppData\\Roaming\\.minecraft"
    assert (
        detect_launcher("/h/.lunarclient/profiles/1.8/logs/latest.log")["minecraft_dir"]
        == "/h/.minecraft"
    )

    prism = detect_launcher(
        f"{HOME}\\AppData\\Roaming\\PrismLauncher\\instances\\X\\minecraft"
        "\\logs\\latest.log"
    )
    assert prism["launcher_dir"] == f"{HOME}\\AppData\\Roaming\\PrismLauncher"
    assert prism["instance_dir"] == (
        f"{HOME}\\AppData\\Roaming\\PrismLauncher\\instances\\X"
    )


def test_parse_log_head() -> None:
    text = "\n".join(
        (
            "[20:25:20] [Client thread/INFO]: Setting user: Player",
            "[20:25:20] [Client thread/INFO]: (Session ID is token:eyJsecret:abc)",
            "[16:32:08] [main/INFO]: Forge Mod Loader version 11.15.1.2318 for "
            "Minecraft 1.8.9 loading",
            "[16:32:08] [main/INFO]: Java is Java HotSpot(TM) 64-Bit Server VM, "
            "version 1.8.0_51, running on Windows 10:amd64:10.0, installed at C:\\x",
            "[20:11:29] [Client thread/INFO]: LWJGL Version: 2.9.4",
            "[20:11:29] [Client thread/INFO]: [STDOUT]: LUNARCLIENT_STATUS_INIT",
            "[20:11:29] [Client thread/INFO]: [OptiFine] OptiFine_1.8.9_HD_U_M6_pre2",
            "[16:33:04] [Client thread/INFO]: MC Version: 1.8",
            "[16:33:04] [Client thread/INFO]: BLC Version: v3.15.2-3c53b96-PROD",
            "[16:33:04] [Client thread/INFO]: Width: 1280",
            "[16:33:04] [Client thread/INFO]: Height: 720",
            "[16:33:04] [Client thread/INFO]: FullScreen: false",
            "[17:57:52] [main/INFO]: Loading Minecraft 26.3 with Fabric Loader 0.19.5",
        )
    )
    result = parse_log_head(text)
    assert result == {
        "first_line_time": "20:25:20",
        "user": "Player",
        "forge": "11.15.1.2318",
        "minecraft": "1.8.9",
        "java": "1.8.0_51",
        "lwjgl": "2.9.4",
        "lunar": True,
        "optifine": "1.8.9_HD_U_M6_pre2",
        "badlion_mc": "1.8",
        "badlion": "v3.15.2-3c53b96-PROD",
        "badlion_width": "1280",
        "badlion_height": "720",
        "badlion_fullscreen": "false",
        "fabric": "0.19.5",
        "fabric_minecraft": "26.3",
    }
    assert "eyJsecret" not in json.dumps(result)


def test_parse_log_head_empty() -> None:
    assert parse_log_head("") == {"first_line_time": None}


def test_parse_options() -> None:
    text = 'guiScale:2\nresourcePacks:["a.zip","b"]\nlang:en_US\nbad line\nx:y:z\n'
    assert parse_options(text) == {
        "guiScale": "2",
        "resourcePacks": '["a.zip","b"]',
        "lang": "en_US",
        "x": "y:z",
    }


def test_parse_options_json() -> None:
    assert parse_options('{"guiScale": "3", "n": 1}') == {"guiScale": "3", "n": 1}


@pytest.mark.parametrize(
    "args, expected",
    (
        (
            ["java", "--accessToken", "abc", "--version", "1.8.9"],
            ["java", "--accessToken", "<redacted>", "--version", "1.8.9"],
        ),
        (["java", "--accessToken=abc"], ["java", "--accessToken=<redacted>"]),
        (["java", "eyJhbGciOi.x.y"], ["java", "<redacted>"]),
        (
            ["x", "--xuid", "1", "--clientId", "2", "--session", "3"],
            ["x", "--xuid", "<redacted>", "--clientId", "<redacted>"]
            + ["--session", "<redacted>"],
        ),
        (["x", "--accessToken"], ["x", "--accessToken"]),
    ),
)
def test_redact_cmdline(args: list[str], expected: list[str]) -> None:
    assert redact_cmdline(args) == expected


def test_parse_cmdline() -> None:
    args = [
        "javaw.exe",
        "-Xmx3G",
        "-Djava.library.path=C:\\natives",
        "--version",
        "1.8.9",
        "--gameDir",
        "C:\\g",
        "--assetIndex",
        "1.8",
        "--launcherVersion",
        "3.2.1",
        "--texturesDir",
        "C:\\t",
        "--width",
        "854",
        "--accessToken",
        "secret",
    ]
    assert parse_cmdline(args) == {
        "version": "1.8.9",
        "gameDir": "C:\\g",
        "assetIndex": "1.8",
        "launcherVersion": "3.2.1",
        "texturesDir": "C:\\t",
        "width": "854",
        "xmx": "3G",
    }


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf8")


def test_collect_game_info_lunar(tmp_path: Path) -> None:
    home = tmp_path / "home"
    profile = home / ".lunarclient" / "profiles" / "1.8"
    logfile = profile / "logs" / "latest.log"
    _write(logfile, "[20:11:28] [Client thread/INFO]: Setting user: Me\n")
    _write(profile / "options.txt", 'guiScale:2\nresourcePacks:["p.zip"]\n')
    _write(profile / "optionsof.txt", "ofCustomFonts:true\n")
    _write(profile / "optionsLC.txt", '{"guiScale":"3","lastLaunchedVersion":"v1"}')
    _write(profile / "resourcepacks" / "p.zip", "zip")
    (profile / "resourcepacks" / "folderpack").mkdir()
    game = home / ".lunarclient" / "settings" / "game"
    _write(game / "profile_manager.json", "[]")
    _write(game / "accounts.json", '{"token": "secret"}')
    _write(game / "Default" / "mods.json", "{}")
    _write(home / ".minecraft" / "resourcepacks" / "shared.zip", "zip")
    _write(home / ".minecraft" / "optionsLC.txt", "{}")

    out = tmp_path / "out"
    info = collect_game_info(str(logfile), out)

    assert info["logfile"] == str(logfile)
    assert info["launcher"]["launcher"] == "lunar"
    assert info["log_head"]["user"] == "Me"
    assert info["options"]["options.txt"]["guiScale"] == "2"
    assert info["options"]["optionsLC.txt"]["lastLaunchedVersion"] == "v1"
    assert info["options"]["optionsof.txt"] == {"ofCustomFonts": "true"}
    assert info["resourcepacks_dir"] == ["folderpack", "p.zip"]
    assert info["minecraft_resourcepacks_dir"] == ["shared.zip"]

    snapshot = out / info["settings_snapshot"]
    copied = sorted(
        p.relative_to(snapshot).as_posix() for p in snapshot.rglob("*") if p.is_file()
    )
    assert "game/options.txt" in copied
    assert "launcher/settings/game/Default/mods.json" in copied
    assert "launcher/settings/game/profile_manager.json" in copied
    assert "minecraft/optionsLC.txt" in copied
    assert not any("accounts" in name for name in copied)
    assert (snapshot / "manifest.json").is_file()

    # Same content -> same snapshot dir
    again = collect_game_info(str(logfile), out)
    assert again["settings_snapshot"] == info["settings_snapshot"]


def test_active_logfile() -> None:
    set_active_logfile(Path("/a/latest.log"))
    assert get_active_logfile() == str(Path("/a/latest.log"))
    set_active_logfile(None)
    assert get_active_logfile() is None


def test_detect_launcher_pvplounge() -> None:
    result = detect_launcher("/h/.pvplounge/logs/latest.log")
    assert result["launcher"] == "pvplounge"
    assert result["game_dir"] == "/h/.pvplounge"


def test_parse_options_bad_json() -> None:
    assert parse_options("{not json") == {}
    assert parse_options("[1]") == {}


def test_collect_game_info_prismlauncher(tmp_path: Path) -> None:
    instance = tmp_path / "PrismLauncher" / "instances" / "X"
    logfile = instance / "minecraft" / "logs" / "latest.log"
    _write(logfile, "")
    _write(instance / "instance.cfg", "[General]\n")
    _write(instance / "minecraft" / "options.txt", "guiScale:3\n")

    out = tmp_path / "out"
    info = collect_game_info(str(logfile), out)
    snapshot = out / info["settings_snapshot"]
    assert (snapshot / "instance" / "instance.cfg").is_file()
    assert info["options"]["options.txt"] == {"guiScale": "3"}


def test_collect_game_info_snapshot_fails(tmp_path: Path) -> None:
    profile = tmp_path / ".lunarclient" / "profiles" / "1.8"
    logfile = profile / "logs" / "latest.log"
    _write(logfile, "")
    _write(profile / "options.txt", "guiScale:2\n")
    out = tmp_path / "out"
    out.write_text("not a dir")

    info = collect_game_info(str(logfile), out)
    assert info["settings_snapshot"] is None
    assert info["options"] == {}


def test_collect_game_info_no_logfile(tmp_path: Path) -> None:
    info = collect_game_info(None, tmp_path)
    assert info["logfile"] is None
    assert info["settings_snapshot"] is None


def test_collect_game_info_missing_files(tmp_path: Path) -> None:
    info = collect_game_info(str(tmp_path / "nope" / "logs" / "latest.log"), tmp_path)
    assert info["log_head"] is None
    assert info["options"] == {}
