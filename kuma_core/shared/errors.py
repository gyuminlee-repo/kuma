"""JSON-RPC error helpers."""
from __future__ import annotations

from typing import Any, Optional


def jsonrpc_error(code: int, message: str, data: Optional[Any] = None) -> dict:
    err: dict = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return err


class JSONRPCError(Exception):
    def __init__(self, code: int, message: str, data: Optional[Any] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def to_dict(self) -> dict:
        return jsonrpc_error(self.code, self.message, self.data)
