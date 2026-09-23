import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(os.name == "nt", reason="Synthetic loader uses a POSIX shebang")
def test_onedir_build_keeps_loader_dependencies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import build_sidecar as build

    bundle = tmp_path / "dist" / "kuro-sidecar"
    internal = bundle / "_internal"
    internal.mkdir(parents=True)
    (internal / "payload").write_text("dependency", encoding="utf-8")
    executable = bundle / "kuro-sidecar"
    executable.write_text(
        f"#!{sys.executable}\nfrom pathlib import Path\n"
        "print((Path(__file__).parent / '_internal' / 'payload').read_text())\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    monkeypatch.setattr(build, "SCRIPT_DIR", tmp_path)
    monkeypatch.setattr(build, "TAURI_BINARIES", tmp_path / "binaries")
    monkeypatch.setattr(build.platform, "system", lambda: "Linux")
    # This test's bundle is a synthetic shell-script stand-in, not a real
    # PyInstaller archive, so the LGPL packaging check (which parses the
    # actual archive format) is out of scope here and is covered on its own
    # below by test_check_no_excluded_license_payload_*.
    monkeypatch.setattr(build, "check_no_excluded_license_payload", lambda *a, **k: None)
    with monkeypatch.context() as builder:
        builder.setattr(build.subprocess, "run", lambda *args, **kwargs: None)
        built = build.build_sidecar("kuro", onefile=False)

    assert built == bundle
    result = subprocess.run([str(built / "kuro-sidecar")], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "dependency"
    with pytest.raises(ValueError, match="onefile"):
        build.copy_to_tauri("kuro", built)
    assert not (tmp_path / "binaries").exists()
    with monkeypatch.context() as builder:
        builder.setattr(build.subprocess, "run", lambda *args, **kwargs: None)
        builder.setattr(sys, "argv", ["build_sidecar.py", "--target", "kuro", "--onedir"])
        build.main()
    assert not (tmp_path / "binaries").exists()
    assert (built / "_internal" / "payload").read_text() == "dependency"


def test_onefile_copy_preserves_executable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import build_sidecar as build

    executable = tmp_path / "kuro-sidecar"
    executable.write_bytes(b"onefile")
    monkeypatch.setattr(build, "TAURI_BINARIES", tmp_path / "binaries")
    copied = build.copy_to_tauri("kuro", executable)
    assert copied.read_bytes() == executable.read_bytes()


@pytest.mark.parametrize("kind", ["kuro", "mame"])
@pytest.mark.parametrize("mode", ["clean", "crash", "hang"])
@pytest.mark.skipif(os.name == "nt", reason="Synthetic executable peer uses a POSIX shebang")
def test_smoke_rejects_abnormal_shutdown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str, mode: str,
) -> None:
    scripts = Path("python-core/scripts").resolve()
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(f"frozen_{kind}", scripts / f"frozen_{kind}_smoke.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from scripts.smoke_sidecar_io import SidecarIO

    smoke_dir = tmp_path / "smoke"
    smoke_dir.mkdir()
    monkeypatch.setattr(module.tempfile, "mkdtemp", lambda **kwargs: str(smoke_dir))

    class FastDeadlines(SidecarIO):
        def recv(self, req_id: int, timeout: float) -> dict:
            return super().recv(req_id, min(timeout, 2.0))

        def close(self, timeout: float = 10.0) -> int:
            return super().close(min(timeout, 0.2))

    monkeypatch.setattr(module, "SidecarIO", FastDeadlines)
    replies = {
        1: {"ok": True}, 2: {"total_count": 1, "seq_length": 10, "genes": [{"gene": "x"}]},
        3: {"native_barcodes": ["NB06", "NB20"]},
        4: {"verdicts": [], "assigned_reads": 1, "wells_with_reads": 1},
        5: {"native_barcodes": ["NB06"], "assigned_reads": 1},
        6: {"wells_with_reads": 0, "assigned_reads": 0},
    }
    if kind == "mame":
        wells = len(module._GENE_ROWS) * len(module._GENE_COLS)
        replies[6] = {"wells_with_reads": wells, "assigned_reads": wells * module._GENE_READS_PER_WELL}
    peer = tmp_path / "peer"
    peer.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys, time\nfrom pathlib import Path\n"
        f"print('{kind.upper()} sidecar started', file=sys.stderr, flush=True)\n"
        f"replies = {replies!r}\n"
        "if 'KUMA_MAME_TIMING_JSON' in os.environ:\n"
        "    Path(os.environ['KUMA_MAME_TIMING_JSON']).write_text(json.dumps({'phases_s': {'barcode_match_parallel_wall': 1}}))\n"
        "for line in sys.stdin:\n"
        "    req = json.loads(line)\n"
        "    print(json.dumps({'id': req['id'], 'result': replies.get(req['id'], {'ok': True})}), flush=True)\n"
        "    if req['method'] == 'shutdown':\n"
        f"        if {mode!r} == 'hang': time.sleep(30)\n"
        f"        sys.exit(7 if {mode!r} == 'crash' else 0)\n",
        encoding="utf-8",
    )
    peer.chmod(0o755)
    with pytest.raises(SystemExit) as exit_info:
        if kind == "kuro":
            module.run_smoke(peer, Path("fixtures/pSHCE-dmpR.gb"))
        else:
            module.run_smoke(peer)
    assert exit_info.value.code == (0 if mode == "clean" else 1)


# --- LGPL-3.0 vendored-module packaging guard (PR #444 follow-up) ---
#
# setuptools >= 78 vendors ``autocommand`` (LGPL-3.0) under
# ``setuptools._vendor``. ``--exclude-module`` alone cannot keep it out of a
# frozen sidecar (collect_all's data-file walk still ships the raw sources
# and dist-info), so build_sidecar.py inspects the built payload directly.
# These tests inject fabricated entry-name corpora instead of running a real
# PyInstaller build.


@pytest.mark.parametrize(
    "entry_names",
    [
        pytest.param(
            ["setuptools._vendor.autocommand", "setuptools._vendor.autocommand.autocommand"],
            id="onefile-pyz-dotted",
        ),
        pytest.param(
            ["setuptools/_vendor/autocommand/__init__.py"],
            id="onedir-loose-py-source",
        ),
        pytest.param(
            ["setuptools/_vendor/autocommand-2.2.2.dist-info/METADATA"],
            id="onedir-dist-info-versioned",
        ),
        pytest.param(
            ["setuptools\\_vendor\\autocommand\\__init__.py"],
            id="onedir-windows-backslash-py-source",
        ),
        pytest.param(
            ["setuptools\\_vendor\\autocommand-2.2.2.dist-info\\METADATA"],
            id="onedir-windows-backslash-dist-info",
        ),
    ],
)
def test_find_excluded_license_payload_catches_autocommand(entry_names: list[str]) -> None:
    import build_sidecar as build

    hits = build.find_excluded_license_payload(entry_names, build.LGPL_EXCLUDED_MODULE)
    assert hits == sorted(entry_names)


@pytest.mark.parametrize(
    "entry_names",
    [
        pytest.param(
            [
                "setuptools._vendor.jaraco.context",
                "setuptools._vendor.backports.tarfile",
                "numpy.core._multiarray_umath",
                "primer3",
            ],
            id="permissive-vendor-siblings",
        ),
        pytest.param(
            ["setuptools/_vendor/jaraco/text/__init__.py"],
            id="onedir-permissive-sibling-source",
        ),
        pytest.param(
            ["setuptools\\_vendor\\jaraco\\text\\__init__.py"],
            id="onedir-windows-backslash-permissive-sibling",
        ),
        pytest.param(
            ["some_autocommand_helper", "setuptools._vendor.autocommandish"],
            id="substring-trap-not-a-path-segment",
        ),
        pytest.param([], id="empty"),
    ],
)
def test_find_excluded_license_payload_passes_clean_corpus(entry_names: list[str]) -> None:
    import build_sidecar as build

    assert build.find_excluded_license_payload(entry_names, build.LGPL_EXCLUDED_MODULE) == []


def test_check_no_excluded_license_payload_fails_build_on_hit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import build_sidecar as build

    monkeypatch.setattr(
        build,
        "_packaged_entry_names",
        lambda built_path, onefile: {"setuptools._vendor.autocommand.autocommand"},
    )
    with pytest.raises(SystemExit) as exit_info:
        build.check_no_excluded_license_payload(tmp_path / "kuro-sidecar", onefile=True)
    assert exit_info.value.code == 1


def test_check_no_excluded_license_payload_passes_clean_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import build_sidecar as build

    monkeypatch.setattr(
        build,
        "_packaged_entry_names",
        lambda built_path, onefile: {"setuptools._vendor.jaraco.context", "numpy"},
    )
    build.check_no_excluded_license_payload(tmp_path / "kuro-sidecar", onefile=False)
