"""Native Windows framing has injectable byte reads for host-independent tests."""
from __future__ import annotations

from collections import deque

import pytest

from kuma_core.shared.windows_rpc import BoundedUtf8LineReader, RpcLineError, CHUNK_BYTES


def reader(*chunks: bytes, limit=64):
    remaining = deque(chunks)
    return BoundedUtf8LineReader(lambda: remaining.popleft() if remaining else b"", limit=limit)


def test_fragmented_utf8_crlf_multiple_frames_and_final_unterminated_line():
    stream = reader(b'{"text":"\xe9', b'\x9f', b'\x93"}\r\n{}\nlast')
    assert stream.readline() == '{"text":"韓"}\r\n'
    assert stream.readline() == '{}\n'
    assert stream.readline() == 'last'
    assert stream.readline() == ''
    assert stream.readline() == ''


def test_buffered_following_frame_does_not_require_another_read():
    calls = []
    def read():
        calls.append(1)
        if len(calls) != 1:
            raise AssertionError("Unexpected next-request read")
        return b'one\ntwo\n'
    stream = BoundedUtf8LineReader(read)
    assert stream.readline() == 'one\n'
    assert stream.readline() == 'two\n'
    assert len(calls) == 1


@pytest.mark.parametrize("chunks", [(b'12345\n{}\n',), (b'12345', b'67', b'\n{}\n')])
def test_oversized_line_is_drained_once_and_later_frame_survives(chunks):
    stream = reader(*chunks, limit=4)
    with pytest.raises(RpcLineError, match="exceeds"):
        stream.readline()
    assert stream.readline() == '{}\n'
    assert stream.readline() == ''


def test_oversized_unterminated_eof_is_reported_once():
    stream = reader(b'12345', b'678', limit=4)
    with pytest.raises(RpcLineError, match="exceeds"):
        stream.readline()
    assert stream.readline() == ''


def test_invalid_utf8_consumes_only_one_frame():
    stream = reader(b'\xff\n{}\n')
    with pytest.raises(RpcLineError, match="UTF-8"):
        stream.readline()
    assert stream.readline() == '{}\n'
    stream = reader(b'\xe9')
    with pytest.raises(RpcLineError, match="UTF-8"):
        stream.readline()
    assert stream.readline() == ''


def test_bounded_chunk_and_os_errors_fail_without_reinterpreting_as_eof():
    stream = reader(b'x' * (CHUNK_BYTES + 1))
    with pytest.raises(OSError, match="bounded"):
        stream.readline()
    def failed_read():
        raise OSError("injected native read failure")
    with pytest.raises(OSError, match="injected"):
        BoundedUtf8LineReader(failed_read).readline()


def test_exact_limit_and_empty_frames():
    stream = reader(b'123\n\n\r\n', limit=4)
    assert stream.readline() == '123\n'
    assert stream.readline() == '\n'
    assert stream.readline() == '\r\n'


def test_oversized_drain_memory_stays_bounded():
    count = 0
    stream = None
    def read():
        nonlocal count
        assert stream is not None
        assert len(stream._pending) <= 32
        count += 1
        return b'x' * 1024 if count < 100 else b'\n{}\n'
    stream = BoundedUtf8LineReader(read, limit=32)
    with pytest.raises(RpcLineError):
        stream.readline()
    assert stream.readline() == '{}\n'


def test_native_windows_pipe_read_releases_gil_and_handles_unicode_eof():
    import os
    import queue
    import subprocess
    import sys
    import threading
    if os.name != "nt":
        pytest.skip("Native Windows ReadFile probe")
    source = '''import sys, threading, time
from kuma_core.shared.windows_rpc import windows_stdin_reader
reader = windows_stdin_reader(sys.stdin.fileno())
def progress():
    time.sleep(0.05)
    print("worker-progress", flush=True)
threading.Thread(target=progress, daemon=True).start()
line = reader.readline()
print(line.encode("utf-8").hex(), flush=True)
assert reader.readline() == ""
'''
    process = subprocess.Popen([sys.executable, "-c", source], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert process.stdin is not None and process.stdout is not None
    messages: queue.Queue[bytes] = queue.Queue()
    def read_output():
        assert process.stdout is not None
        for line in process.stdout:
            messages.put(line)
    threading.Thread(target=read_output, daemon=True).start()
    try:
        # No second request/input is available; a worker must still progress.
        assert messages.get(timeout=10).strip() == b"worker-progress"
        raw = '"韓"\r\n'.encode()
        process.stdin.write(raw)
        process.stdin.flush()
        assert messages.get(timeout=10).strip() == raw.hex().encode()
        process.stdin.close()
        assert process.wait(timeout=10) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()
