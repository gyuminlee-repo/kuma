"""Start-method selection for the MAME demux ProcessPools.

Guards the one thing that must never regress: a frozen (PyInstaller) build has
to keep using "spawn". multiprocessing.forkserver.ensure_running launches its
helper as ``[sys.executable, ..., "-c", <code>]`` with no ``sys.frozen`` branch
(unlike multiprocessing.spawn.get_command_line), so inside a bundle it would
re-exec the sidecar binary instead of starting a forkserver.
"""

from __future__ import annotations

import multiprocessing
import sys

import pytest

from kuma_core.mame.ingest import combinatorial_demux as cd

_POSIX_ONLY = pytest.mark.skipif(
    "forkserver" not in multiprocessing.get_all_start_methods(),
    reason="forkserver is POSIX only",
)


@_POSIX_ONLY
def test_default_is_forkserver_when_not_frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KUMA_MAME_MP_START", raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert cd._mp_start_method() == "forkserver"


@_POSIX_ONLY
def test_frozen_build_stays_on_spawn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KUMA_MAME_MP_START", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert cd._mp_start_method() == "spawn"


def test_env_override_forces_spawn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("KUMA_MAME_MP_START", "SPAWN")
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert cd._mp_start_method() == "spawn"


def test_unavailable_override_falls_back_to_spawn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KUMA_MAME_MP_START", "not-a-start-method")
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert cd._mp_start_method() == "spawn"


@_POSIX_ONLY
def test_context_carries_the_preload_and_warmup_is_noop_for_spawn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorded: list[list[str]] = []
    monkeypatch.setattr(
        "multiprocessing.forkserver.set_forkserver_preload",
        lambda names: recorded.append(list(names)),
    )
    monkeypatch.setenv("KUMA_MAME_MP_START", "forkserver")
    ctx = cd._demux_mp_context()
    assert ctx.get_start_method() == "forkserver"
    assert recorded == [list(cd._MP_PRELOAD)]

    monkeypatch.setenv("KUMA_MAME_MP_START", "spawn")
    spawn_ctx = cd._demux_mp_context()
    assert spawn_ctx.get_start_method() == "spawn"
    assert cd._warm_mp_context(spawn_ctx) is None
