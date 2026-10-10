"""Bounded UTF-8 framing over a native Windows stdin pipe.

WinDLL calls release the GIL while ReadFile blocks. This establishes a concrete
worker-progress contract; it is not a diagnosis of the historical frozen I/O
stall. Use this reader from process startup, never after TextIOWrapper read-ahead.
The stdio handle belongs to the host and is not closed here.
"""
from __future__ import annotations

import ctypes
import os
import time
from collections.abc import Callable
from ctypes import wintypes

CHUNK_BYTES = 16 * 1024
MAX_RPC_LINE_BYTES = 64 * 1024 * 1024


class RpcLineError(ValueError):
    """One malformed/oversized frame was consumed; later frames remain readable."""


class BoundedUtf8LineReader:
    def __init__(self, read_chunk: Callable[[], bytes], *, limit: int = MAX_RPC_LINE_BYTES):
        if type(limit) is not int or limit < 1:
            raise ValueError("Invalid RPC line limit")
        self._read = read_chunk
        self._limit = limit
        self._pending = bytearray()
        self._eof = False
        self._discard = False

    def readline(self) -> str:
        while True:
            newline = self._pending.find(b"\n")
            if newline >= 0:
                # Framing consumes the bad line before raising, preserving the
                # following requests even when ReadFile returned them together.
                size = newline + 1
                if self._discard or size > self._limit:
                    del self._pending[:size]
                    self._discard = False
                    raise RpcLineError("RPC line exceeds the 64 MiB byte limit")
                raw = bytes(self._pending[:size])
                del self._pending[:size]
                return self._decode(raw)
            if len(self._pending) > self._limit:
                self._discard = True
            if self._discard:
                self._pending.clear()
            if self._eof:
                if self._discard:
                    self._discard = False
                    raise RpcLineError("RPC line exceeds the 64 MiB byte limit")
                raw = bytes(self._pending)
                self._pending.clear()
                return self._decode(raw)
            chunk = self._read()
            if not isinstance(chunk, bytes) or len(chunk) > CHUNK_BYTES:
                raise OSError("Invalid bounded RPC pipe read")
            if not chunk:
                self._eof = True
            else:
                self._pending.extend(chunk)

    @staticmethod
    def _decode(raw: bytes) -> str:
        try:
            return raw.decode("utf-8")
        except UnicodeError as exc:
            raise RpcLineError("RPC input must be valid UTF-8") from exc


def windows_stdin_reader(fd: int) -> BoundedUtf8LineReader:
    """Require a native pipe and use explicit GIL-releasing WinDLL reads."""
    if os.name != "nt":
        raise OSError("Native Windows RPC pipe reader requires Windows")
    import msvcrt

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetFileType.argtypes = [wintypes.HANDLE]
    kernel.GetFileType.restype = wintypes.DWORD
    kernel.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                               ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    kernel.ReadFile.restype = wintypes.BOOL
    handle = msvcrt.get_osfhandle(fd)
    if kernel.GetFileType(handle) != 3:  # FILE_TYPE_PIPE only, never console/file.
        raise OSError("Frozen asynchronous RPC requires a native stdin pipe")
    buffer = ctypes.create_string_buffer(CHUNK_BYTES)

    def read_chunk() -> bytes:
        while True:
            count = wintypes.DWORD()
            if not kernel.ReadFile(handle, buffer, CHUNK_BYTES, ctypes.byref(count), None):
                code = ctypes.get_last_error()
                if code == 109:  # ERROR_BROKEN_PIPE is anonymous-pipe EOF.
                    return b""
                raise OSError(code, "Native RPC pipe read failed")
            if count.value:
                return buffer.raw[:count.value]
            # A successful zero-byte pipe read may be a zero-byte WriteFile,
            # not EOF. Keep other threads running without spinning.
            time.sleep(0.01)

    return BoundedUtf8LineReader(read_chunk)
