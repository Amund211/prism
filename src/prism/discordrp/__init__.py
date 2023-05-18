"""
MIT License

Copyright (c) 2022 TenType

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

Copied from https://github.com/TenType/discord-rich-presence/

Adapted for use in Prism
"""

import json
import os
import socket
import struct
import sys
from collections.abc import Mapping
from enum import IntEnum
from types import TracebackType
from typing import Any, Self
from uuid import uuid4


class OpCode(IntEnum):
    """A list of valid opcodes that can be sent in packets to Discord."""

    HANDSHAKE = 0
    FRAME = 1
    CLOSE = 2
    PING = 3
    PONG = 4


SOCKET_NAME = "discord-ipc-{}"


class PresenceError(Exception):
    """Errors emitted by the Presence class."""


class Presence:
    """The main class used to connect to Discord for its rich presence API."""

    def __init__(self, client_id: str) -> None:
        self.client_id = client_id
        self._socket: Any = None  # Either BufferedWriter or socket

        # Connect to Discord IPC
        self._connect()

        # Send a handshake request
        self._handshake()

    def set(self, activity: Mapping[str, object] | None) -> None:
        """
        Sends an activity payload to Discord.

        :param activity: A dictionary of this format:

        ```
        {
            'state': str,
            'details': str,
            'timestamps': {
                'start': int,
                'end': int,
            },
            'assets': {
                'large_image': str,
                'large_text': str,
                'small_image': str,
                'small_text': str,
            },
            'buttons': [
                {
                    'label': str,
                    'url': str,
                },
                {
                    'label': str,
                    'url': str,
                }
            ],
        }
        ```
        One field of either 'state', 'details', or 'timestamps.start' is required.
        """
        payload = {
            "cmd": "SET_ACTIVITY",
            "args": {
                "pid": os.getpid(),
                "activity": activity,
            },
            "nonce": str(uuid4()),
        }
        self._send(payload, OpCode.FRAME)

    def close(self) -> None:
        """
        Closes the current connection.

        Automatically called when the program exits using the 'with' statement.
        """
        self._send({}, OpCode.CLOSE)
        self._socket.close()

    def _connect(self) -> None:
        pipe = self._get_pipe()

        # Try to connect to a socket, starting from 0 up to 9
        for i in range(10):
            try:
                self._try_socket(pipe, i)
                break
            except FileNotFoundError:
                pass
        else:
            raise PresenceError("Cannot find a socket to connect to Discord")

    def _get_pipe(self) -> str:
        if sys.platform == "win32":
            # Windows pipe
            return R"\\?\pipe\\" + SOCKET_NAME

        # Unix pipe
        for env in ("XDG_RUNTIME_DIR", "TMPDIR", "TMP", "TEMP"):
            path = os.environ.get(env)
            if path is not None:
                return path + SOCKET_NAME

        return "/tmp/" + SOCKET_NAME

    def _try_socket(self, pipe: str, i: int) -> None:
        if sys.platform == "win32":
            self._socket = open(pipe.format(i), "wb")
        else:
            self._socket = socket.socket(socket.AF_UNIX)
            self._socket.connect(pipe.format(i))

    def _handshake(self) -> None:
        data = {
            "v": 1,
            "client_id": self.client_id,
        }
        self._send(data, OpCode.HANDSHAKE)
        _, response = self._read()

        if response.get("evt") != "READY":
            raise PresenceError(
                "Discord returned an error response after a handshake request"
            )

    def _read(self) -> tuple[int, Mapping[str, object]]:
        op, length = self._read_header()
        payload = self._read_bytes(length)
        decoded = payload.decode("utf-8")
        data = json.loads(decoded)
        return op, data

    def _read_header(self) -> tuple[int, int]:
        return struct.unpack("<ii", self._read_bytes(8))  # type: ignore [return-value]

    def _read_bytes(self, size: int) -> bytes:
        encoded = b""
        while size > 0:
            if sys.platform == "win32":
                encoded += self._socket.read(size)
            else:
                encoded += self._socket.recv(size)

            size -= len(encoded)
        return encoded

    def _send(self, payload: Mapping[str, object], op: OpCode) -> None:
        data_json = json.dumps(payload)
        encoded = data_json.encode("utf-8")
        header = struct.pack("<ii", int(op), len(encoded))
        self._write(header + encoded)

    def _write(self, data: bytes) -> None:
        if sys.platform == "win32":
            self._socket.write(data)
            self._socket.flush()
        else:
            self._socket.sendall(data)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType | None,
    ) -> None:
        self.close()
