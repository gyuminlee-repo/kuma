import json
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("scenario", ["complete", "missing", "directory", "duplicate"])
def test_manifest_requires_unique_installer_pairs(tmp_path: Path, scenario: str) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    for name in ("kuma-setup.exe", "kuma.AppImage", "kuma.app.tar.gz"):
        (artifacts / (name + ".sig")).write_text("synthetic-signature", encoding="utf-8")
        if scenario == "directory":
            (artifacts / name).mkdir()
        elif scenario != "missing":
            (artifacts / name).write_bytes(b"synthetic-installer")
    if scenario == "duplicate":
        (artifacts / "other-setup.exe.sig").write_text("signature", encoding="utf-8")
        (artifacts / "other-setup.exe").write_bytes(b"installer")
    output = tmp_path / "latest.json"

    result = subprocess.run(
        ["node", "scripts/gen-latest-json.mjs", "v0.16.63", str(artifacts), str(output)],
        capture_output=True, text=True, timeout=15, check=False,
    )

    print(scenario, result.returncode, result.stdout, result.stderr)
    if scenario == "complete":
        assert result.returncode == 0, result.stderr
        manifest = json.loads(output.read_text())
        assert len(manifest["platforms"]) == 3
        assert manifest["platforms"]["windows-x86_64"]["url"].endswith("/kuma-setup.exe")
    else:
        assert result.returncode != 0
        assert not output.exists()
