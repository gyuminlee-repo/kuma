"""Shared helpers for Python sidecar processes."""

from __future__ import annotations

import datetime
import json
import math
import os
import sys
import threading
from pathlib import Path
from typing import Any

from kuma_core.shared.errors import jsonrpc_error

CRASH_LOG_MAX_ENTRIES = 50

# JSON-RPC "Internal error". Chosen deliberately over -32602/-32700: the request
# itself was well formed and the parameters were valid, so the fault is entirely
# server side. The sidecar computed a value (NaN / Infinity) that JSON cannot
# represent, which is exactly "an internal error of the server".
JSONRPC_INTERNAL_ERROR = -32603

# How many offending field paths to name in the error message. The count of all
# offenders is reported separately, so truncating the list stays honest.
NON_FINITE_PATHS_REPORTED = 5


def find_non_finite_paths(
    obj: Any,
    *,
    prefix: str = "",
    _ancestors: frozenset[int] = frozenset(),
) -> list[str]:
    """Return dotted/indexed paths of every non-finite float inside ``obj``.

    Used to turn an unserialisable JSON-RPC payload into a message that names
    the offending cell (``result.tm``, ``result.rows[3].gc``) instead of only
    stating that some value was non-finite.

    ``_ancestors`` tracks the containers currently on the walk path so a
    circular payload terminates instead of recursing forever. Tracking only the
    ancestors (not every container ever seen) keeps repeated, non-cyclic
    references fully searched.
    """
    if isinstance(obj, float) and not math.isfinite(obj):
        return [prefix or "<root>"]
    if not isinstance(obj, (dict, list, tuple)):
        return []
    if id(obj) in _ancestors:
        return []

    ancestors = _ancestors | {id(obj)}
    found: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            found.extend(find_non_finite_paths(value, prefix=child, _ancestors=ancestors))
    else:
        for index, value in enumerate(obj):
            found.extend(
                find_non_finite_paths(value, prefix=f"{prefix}[{index}]", _ancestors=ancestors)
            )
    return found


def describe_non_finite(paths: list[str]) -> str:
    """Human-readable summary naming the first few offending paths."""
    head = ", ".join(paths[:NON_FINITE_PATHS_REPORTED])
    if len(paths) > NON_FINITE_PATHS_REPORTED:
        head += ", ..."
    noun = "value" if len(paths) == 1 else "values"
    return (
        f"Sidecar produced {len(paths)} non-finite {noun} (NaN/Infinity) "
        f"that JSON cannot represent: {head}"
    )


class _NonFiniteLiteral(Exception):
    """Internal signal raised by a decoder hook.

    The hooks below run inside the C scanner and do not know the request line,
    which :class:`json.JSONDecodeError` needs. They raise this instead and
    :func:`loads_rpc_request` converts it, so callers still see only the
    documented exception type.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def _refuse_constant(literal: str) -> Any:
    """parse_constant hook: the bare ``NaN`` / ``Infinity`` / ``-Infinity`` tokens."""
    raise _NonFiniteLiteral(
        f"{literal} is not valid JSON and cannot be compared against any "
        "threshold; send a finite number or omit the field"
    )


def _refuse_overflowing_float(literal: str) -> float:
    """parse_float hook: a *valid* number literal whose value is not finite.

    ``1e400`` is a well-formed JSON number, so ``parse_constant`` never sees
    it, yet converting it to a double overflows to infinity. Refusing only the
    three bare tokens therefore refused the spelling and admitted the value.

    Underflow is deliberately not refused: ``1e-400`` becomes ``0.0``, which is
    finite and compares normally. Rejecting it would turn this guard into a
    precision policy, which is a different question.
    """
    value = float(literal)
    if not math.isfinite(value):
        # Saying "is not valid JSON" here, as the constant path does, would be
        # a false statement: this literal is valid JSON. Only its value is
        # unusable.
        raise _NonFiniteLiteral(
            f"{literal} overflows to {value} and cannot be compared against "
            "any threshold; send a finite number or omit the field"
        )
    return value


# Built once, at import. ``json.loads`` reuses its cached default decoder only
# when no hook argument is given, so passing hooks to it constructs a fresh
# JSONDecoder on every request. Reusing this one pays that construction back:
# measured on this machine (Python 3.12), a 149-byte request costs 0.0008 ms
# here against 0.0017 ms for the previous ``json.loads(..., parse_constant=)``.
# The parse_float hook is one Python call per float literal and costs nothing
# on a payload without floats (49.7 kB, 0 floats: 0.0253 ms against 0.0270 ms).
# A float-heavy request pays for it: 71.6 kB with 4801 floats costs 0.5506 ms
# against 0.3604 ms, i.e. +0.19 ms on a request whose handler then reads
# several spreadsheets. Walking the decoded structure instead was measured at
# 1.52 ms on the same payload (+183%) and 0.0915 ms on the float-free one
# (+261%), because it visits every node of every request rather than only the
# float literals.
_RPC_DECODER = json.JSONDecoder(
    parse_constant=_refuse_constant,
    parse_float=_refuse_overflowing_float,
)


def loads_rpc_request(line: str) -> Any:
    """Parse one JSON-RPC line, refusing every non-finite value.

    Python's JSON parser accepts bare ``NaN``, ``Infinity`` and ``-Infinity``
    tokens, which no other JSON implementation emits and RFC 8259 does not
    describe. Accepting them puts a value into a handler's parameters that no
    threshold comparison can use: every comparison against NaN is False, so a
    gate given ``{"min_qscore": NaN}`` keeps every read and reports that it
    passed rather than that it could not decide.

    Refusing those three spellings is not enough. ``1e400`` is a valid JSON
    number that overflows to infinity when converted to a double, so it slipped
    past a ``parse_constant``-only guard and arrived as ``inf``. Both the token
    and the overflowing literal are refused here, at any depth, because the
    hooks fire per literal wherever it sits.

    This is the outermost place that can say no. Each handler still guards its
    own numbers (:func:`parse_finite_float`), because a value read from a file
    never passes through here, but a parameter refused at the door cannot reach
    any of them.

    The contract both stdin loops rely on is that this function either returns
    a request or raises something they answer with ``-32700``. ``json`` does
    not honour that on its own: a number literal of more than 4300 digits makes
    the parser raise a plain ``ValueError`` from the interpreter integer-string
    limit, and a deeply nested payload raises ``RecursionError`` (measured on
    Python 3.12, the boundary sits between 5000 and 10000 levels).
    Neither is a ``JSONDecodeError``, so both unwound straight out of ``main``
    and the sidecar process exited (measured: exit code 1, the request
    unanswered, and every later request on that session lost). One malformed
    line killed the session.

    Both are converted here. The conversion is deliberately not a bare
    ``except Exception``: :meth:`JSONDecoder.decode` does exactly one thing,
    parse this string, so a ``ValueError`` or a ``RecursionError`` out of it is
    a statement about the line. A ``TypeError`` or an ``AttributeError`` would
    be a statement about this module, and answering that with a parse error
    would blame the caller for a defect here and hide it.

    Raises:
        json.JSONDecodeError: The line is not JSON, is not parseable, or
            carries a non-finite value. The same type every way, so callers
            that already answer a parse error keep working unchanged.
    """
    try:
        return _RPC_DECODER.decode(line)
    except _NonFiniteLiteral as exc:
        raise json.JSONDecodeError(exc.message, line, 0) from None
    except json.JSONDecodeError:
        # Already the documented type, with the parser's own position. Rewriting
        # it would lose the column it points at.
        raise
    except (ValueError, RecursionError) as exc:
        raise json.JSONDecodeError(
            f"{type(exc).__name__} while parsing the request line: {exc}",
            line,
            0,
        ) from exc


def parse_finite_float(value: Any, *, field: str) -> float:
    """Return ``value`` as a float, refusing NaN and the infinities.

    ``float("nan")`` and ``float("inf")`` both succeed, so a plain ``float()``
    on a caller-supplied threshold or a value read out of a file admits them.
    What follows is almost always a comparison, and every comparison against
    NaN is False: a quality filter written as ``if score < minimum`` keeps the
    read, and a gate written as ``if fraction > limit`` passes it. The gate does
    not report that it could not decide; it reports that the value was fine.
    Infinity fails the same way in the opposite direction, and a bound of
    ``inf`` silently means "no bound".

    This is the guard for a value coming *in*. :func:`find_non_finite_paths`
    guards a payload going *out*, where the same number would break JSON.

    Raises:
        ValueError: *value* is not a number, or is not finite. The message
            names *field* so the caller learns which input was rejected.
    """
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number, got {value!r}") from exc
    if not math.isfinite(parsed):
        raise ValueError(
            f"{field} must be finite, got {parsed!r}. A non-finite bound "
            f"disables the comparison it is used in rather than widening it."
        )
    return parsed


def ensure_private_dir(path: Path) -> Path:
    """Create a user-private directory where platforms support chmod."""
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform != "win32":
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass
    return path


def append_crash_log(
    log_path: Path,
    method: str,
    params_summary: str,
    tb: str,
    *,
    max_entries: int = CRASH_LOG_MAX_ENTRIES,
) -> None:
    """Append one bounded crash-log entry. Logging failures are intentionally ignored."""
    try:
        ensure_private_dir(log_path.parent)
        entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "method": method,
            "params": params_summary[:200],
            "traceback": tb[:2000],
        }
        entries: list[dict[str, Any]] = []
        if log_path.exists():
            try:
                raw = log_path.read_text(encoding="utf-8").strip()
                if raw:
                    loaded = json.loads(raw)
                    entries = loaded if isinstance(loaded, list) else []
            except (json.JSONDecodeError, OSError):
                entries = []
        entries.append(entry)
        del entries[:-max_entries]
        log_path.write_text(
            json.dumps(entries, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


class JsonRpcWriter:
    """Thread-safe stdout writer for JSON-RPC sidecar messages."""

    def __init__(self) -> None:
        self._lock = threading.Lock()

    def send(self, obj: dict[str, Any]) -> None:
        # allow_nan=False turns a non-finite float into a ValueError instead of
        # bare `NaN` / `Infinity` tokens, which are not valid JSON. The Rust
        # client parses with serde_json (strict), dropped the malformed line,
        # and the caller then waited out its full 60s RPC timeout with a
        # transport-shaped error message for what is a data defect.
        try:
            line = json.dumps(obj, ensure_ascii=False, allow_nan=False) + "\n"
        except ValueError:
            paths = find_non_finite_paths(obj)
            if not paths:
                # ValueError here means something else (circular reference).
                # Masking it with a non-finite message would hide a real bug.
                raise
            self._send_non_finite_failure(obj, paths)
            return
        self._write_line(line)

    def _send_non_finite_failure(self, obj: dict[str, Any], paths: list[str]) -> None:
        """Report a payload that cannot be serialised, without inventing values.

        No substitution happens here on purpose: replacing a non-finite number
        with null/0/"" would make a failed computation indistinguishable from a
        legitimately absent value.
        """
        message = describe_non_finite(paths)
        req_id = obj.get("id")
        if req_id is None:
            # A notification (progress / ready) has no id, so it cannot carry a
            # JSON-RPC error response. Emitting anything on stdout would either
            # be malformed or resolve a pending entry that does not exist.
            print(f"[sidecar] dropped notification: {message}", file=sys.stderr, flush=True)
            return
        # Built from strings and the original id only, so this dict is always
        # serialisable; it never re-enters the failure path above.
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": jsonrpc_error(JSONRPC_INTERNAL_ERROR, message, {"paths": paths}),
        }
        print(f"[sidecar] {message}", file=sys.stderr, flush=True)
        self._write_line(json.dumps(payload, ensure_ascii=False, allow_nan=False) + "\n")

    def _write_line(self, line: str) -> None:
        with self._lock:
            if getattr(sys, "frozen", False):
                # Frozen builds (PyInstaller): bypass the TextIOWrapper buffer and
                # write straight to the stdout fd. On Windows the buffered writer
                # withheld messages emitted from worker threads (async analyze/demux
                # responses + progress) until the main thread next touched stdout,
                # so the client only saw a response after sending its NEXT request.
                # A direct os.write delivers each message immediately from any thread.
                data = line.encode("utf-8")
                fd = sys.stdout.fileno()
                while data:
                    data = data[os.write(fd, data):]
            else:
                sys.stdout.write(line)
                sys.stdout.flush()

    def ok(self, req_id: Any, result: Any) -> None:
        self.send({"jsonrpc": "2.0", "id": req_id, "result": result})

    def error(self, req_id: Any, code: int, message: str) -> None:
        self.send({"jsonrpc": "2.0", "id": req_id, "error": jsonrpc_error(code, message)})

    def progress(self, value: int, message: str = "") -> None:
        self.send(
            {
                "jsonrpc": "2.0",
                "method": "progress",
                "params": {"value": value, "message": message},
            }
        )


def _validate_path_common(path_value: str | None, *, value_name: str) -> tuple[Path, Path]:
    if not path_value:
        raise FileNotFoundError(f"{value_name} is required")

    original = Path(path_value)
    if original.is_symlink():
        raise FileNotFoundError(f"Symbolic links are not allowed: {path_value}")
    if ".." in original.parts:
        raise FileNotFoundError(f"Path traversal is not allowed: {path_value}")

    resolved = original.resolve()
    if resolved.is_symlink():
        raise FileNotFoundError(f"Symbolic links are not allowed (resolved): {path_value}")
    return original, resolved


def _validate_extension(resolved: Path, allowed_extensions: set[str] | None) -> None:
    if allowed_extensions is None:
        return
    ext = resolved.suffix.lower()
    if ext not in allowed_extensions:
        raise ValueError(
            f"Unsupported file extension '{ext}'. Allowed: {sorted(allowed_extensions)}"
        )


def validate_filepath(
    filepath: str | None,
    *,
    allowed_extensions: set[str] | None = None,
    must_exist: bool = True,
) -> Path:
    """Validate and resolve an input file path."""
    _, resolved = _validate_path_common(filepath, value_name="filepath")
    if must_exist and not resolved.exists():
        raise FileNotFoundError(f"File does not exist: {filepath}")
    if resolved.is_dir():
        raise FileNotFoundError(f"Path is a directory, not a file: {filepath}")
    _validate_extension(resolved, allowed_extensions)
    return resolved


def validate_dirpath(dirpath: str | None) -> Path:
    """Validate and resolve an existing directory path."""
    _, resolved = _validate_path_common(dirpath, value_name="dirpath")
    if not resolved.exists():
        raise FileNotFoundError(f"Directory does not exist: {dirpath}")
    if not resolved.is_dir():
        raise FileNotFoundError(f"Path is not a directory: {dirpath}")
    return resolved


def validate_output_path(filepath: str | None, *, allowed_extensions: set[str]) -> Path:
    """Validate an output path whose parent must already exist."""
    _, resolved = _validate_path_common(filepath, value_name="filepath")
    if not resolved.parent.exists():
        raise FileNotFoundError(f"Parent directory does not exist: {resolved.parent}")
    _validate_extension(resolved, allowed_extensions)
    return resolved
