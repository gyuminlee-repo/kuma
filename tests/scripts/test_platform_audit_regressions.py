"""Inert packaging contract regressions. No install/network hook is run."""
import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def artifacts(tmp_path):
    folder = tmp_path / "artifacts"
    folder.mkdir()
    for name in ("kuma-setup.exe", "kuma.AppImage", "kuma.app.tar.gz"):
        (folder / name).write_bytes(b"inert fixture")
        (folder / (name + ".sig")).write_text("inert signature", encoding="utf-8")
    return folder


@pytest.mark.parametrize("tag,version", [("v0.16.73.1", "0.16.73"), ("v0.16.73", "0.16.73")])
def test_updater_uses_three_part_app_version_and_retains_tag(tmp_path, tag, version):
    output = tmp_path / "latest.json"
    result = subprocess.run(["node", str(ROOT / "scripts/gen-latest-json.mjs"), tag,
                             str(artifacts(tmp_path)), str(output)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["version"] == version
    assert f"/download/{tag}/" in data["platforms"]["linux-x86_64"]["url"]
    assert tag in data["notes"]


@pytest.mark.parametrize("tag", ["v00.16.73", "v18446744073709551616.1.0"])
def test_updater_refuses_noncanonical_semver_tag(tmp_path, tag):
    output = tmp_path / "latest.json"
    output.write_text("existing manifest", encoding="utf-8")
    result = subprocess.run(["node", str(ROOT / "scripts/gen-latest-json.mjs"), tag,
                             str(artifacts(tmp_path)), str(output)], capture_output=True, text=True)
    assert result.returncode != 0
    assert output.read_text(encoding="utf-8") == "existing manifest"


@pytest.mark.skipif(os.name == "nt", reason="POSIX signal fixture")
def test_install_signal_failure_is_not_success_and_does_not_run_hooks(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "pnpm"
    fake.write_text("#!/bin/sh\nkill -TERM $$\n", encoding="utf-8")
    fake.chmod(0o700)
    result = subprocess.run(["node", str(ROOT / "scripts/safe-install.mjs")],
                            cwd=tmp_path, env={**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"},
                            capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert "SIGTERM" in result.stderr
    assert "install-git-hooks" not in result.stderr
