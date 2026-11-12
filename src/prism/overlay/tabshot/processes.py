"""
Trial branch: running game / launcher processes, with redacted command lines.
Best effort, slow on Windows (PowerShell), so the result is cached.
"""

import json
import logging
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from prism.overlay.tabshot.game_info import parse_cmdline, redact_cmdline

logger = logging.getLogger(__name__)

CACHE_SECONDS = 30.0
PROCESS_NAME_PATTERN = re.compile(
    r"java|lunar|badlion|feather|prismlauncher|multimc|minecraft|labymod|"
    r"modrinth|curseforge|atlauncher|tlauncher|gdlauncher",
    re.IGNORECASE,
)

_POWERSHELL_SCRIPT = (
    "Get-CimInstance Win32_Process | Where-Object { $_.Name -match '"
    + PROCESS_NAME_PATTERN.pattern
    + "' } | ForEach-Object { [pscustomobject]@{"
    "pid=$_.ProcessId; parent_pid=$_.ParentProcessId; name=$_.Name; "
    "exe=$_.ExecutablePath; cmdline=$_.CommandLine; "
    "created=$(if ($_.CreationDate) { $_.CreationDate.ToString('o') }) } } "
    "| ConvertTo-Json -Compress -Depth 2"
)

_cache: tuple[float, list[dict[str, Any]]] | None = None


def _split_windows_cmdline(cmdline: str) -> list[str]:  # pragma: nocover
    if sys.platform != "win32":
        return [cmdline]

    import ctypes
    from ctypes import wintypes

    shell32 = ctypes.windll.shell32
    shell32.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    shell32.CommandLineToArgvW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_int),
    ]
    count = ctypes.c_int()
    argv = shell32.CommandLineToArgvW(cmdline, ctypes.byref(count))
    if not argv:
        return [cmdline]
    try:
        return [argv[i] for i in range(count.value)]
    finally:
        ctypes.windll.kernel32.LocalFree(argv)


def _windows_processes() -> list[dict[str, Any]]:  # pragma: nocover
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", _POWERSHELL_SCRIPT],
        capture_output=True,
        text=True,
        timeout=20,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    output = completed.stdout.strip()
    if not output:
        return []
    data = json.loads(output)
    rows = data if isinstance(data, list) else [data]
    result = []
    for row in rows:
        cmdline = row.pop("cmdline", None)
        args = _split_windows_cmdline(cmdline) if cmdline else []
        result.append(_with_args(row, args))
    return result


def _linux_processes() -> list[dict[str, Any]]:  # pragma: nocover
    result = []
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            args = [
                arg.decode("utf8", errors="replace")
                for arg in (proc / "cmdline").read_bytes().split(b"\0")
                if arg
            ]
            name = (proc / "comm").read_text().strip()
            stat = (proc / "stat").read_text()
            exe = str((proc / "exe").resolve()) if (proc / "exe").exists() else None
        except OSError:
            continue
        if not args or not PROCESS_NAME_PATTERN.search(" ".join((name, args[0]))):
            continue
        parent_pid = int(stat.rsplit(")", 1)[1].split()[1])
        row = {"pid": int(proc.name), "parent_pid": parent_pid, "name": name}
        result.append(_with_args({**row, "exe": exe}, args))
    return result


def _with_args(
    row: dict[str, Any], args: list[str]
) -> dict[str, Any]:  # pragma: nocover
    return {**row, "args": redact_cmdline(args), "summary": parse_cmdline(args)}


def list_processes() -> list[dict[str, Any]] | None:  # pragma: nocover
    """Game / launcher processes. None on failure. Cached for a while."""
    global _cache
    now = time.monotonic()
    if _cache is not None and now - _cache[0] < CACHE_SECONDS:
        return _cache[1]
    try:
        if sys.platform == "win32":
            processes = _windows_processes()
        elif sys.platform == "linux":
            processes = _linux_processes()
        else:
            return None
    except Exception:
        logger.exception("Tabshot: failed to list processes")
        return None
    _cache = (now, processes)
    return processes
