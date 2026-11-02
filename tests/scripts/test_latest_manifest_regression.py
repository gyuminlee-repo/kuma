import json
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_APP_VERSION = json.loads((_REPO / "package.json").read_text(encoding="utf-8"))["version"]


def _artifacts(root: Path) -> Path:
    artifacts = root / "artifacts"
    artifacts.mkdir()
    for name in ("kuma-setup.exe", "kuma.AppImage", "kuma.app.tar.gz"):
        (artifacts / (name + ".sig")).write_text("synthetic-signature", encoding="utf-8")
        (artifacts / name).write_bytes(b"synthetic-installer")
    return artifacts


def _bump_patch(version: str) -> str:
    a, b, c = version.split(".")
    return f"{a}.{b}.{int(c) + 1}"


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
        ["node", "scripts/gen-latest-json.mjs", f"v{_APP_VERSION}", str(artifacts), str(output)],
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


@pytest.mark.parametrize(
    ("tag", "accepted"),
    [
        (f"v{_APP_VERSION}", True),
        # A fourth component labels a rebuild of the same binary.
        (f"v{_APP_VERSION}.1", True),
        # The tag names a version the installer does not carry: the updater
        # would advertise it forever and install the older build each time.
        (f"v{_bump_patch(_APP_VERSION)}", False),
        (f"v{_bump_patch(_APP_VERSION)}.1", False),
    ],
)
def test_manifest_refuses_a_tag_the_app_manifests_do_not_carry(
    tmp_path: Path, tag: str, accepted: bool
) -> None:
    artifacts = _artifacts(tmp_path)
    output = tmp_path / "latest.json"

    result = subprocess.run(
        ["node", str(_REPO / "scripts/gen-latest-json.mjs"), tag, str(artifacts), str(output)],
        capture_output=True, text=True, timeout=15, check=False,
    )

    if accepted:
        assert result.returncode == 0, result.stderr
        assert json.loads(output.read_text())["version"] == _APP_VERSION
    else:
        assert result.returncode != 0
        assert "package.json" in result.stderr
        assert not output.exists()


def test_manifest_refuses_a_tauri_conf_that_disagrees(tmp_path: Path) -> None:
    """package.json alone is not the binary: tauri.conf.json stamps the build."""
    root = tmp_path / "repo"
    (root / "scripts").mkdir(parents=True)
    (root / "src-tauri").mkdir()
    for script in ("gen-latest-json.mjs", "tag-manifest-version.mjs"):
        (root / "scripts" / script).write_text(
            (_REPO / "scripts" / script).read_text(encoding="utf-8"), encoding="utf-8"
        )
    (root / "package.json").write_text('{"version": "1.2.3"}', encoding="utf-8")
    (root / "src-tauri" / "tauri.conf.json").write_text(
        '{"version": "1.2.2"}', encoding="utf-8"
    )
    artifacts = _artifacts(tmp_path)
    output = tmp_path / "latest.json"

    result = subprocess.run(
        ["node", str(root / "scripts/gen-latest-json.mjs"), "v1.2.3", str(artifacts), str(output)],
        capture_output=True, text=True, timeout=15, check=False,
    )

    assert result.returncode != 0
    assert "tauri.conf.json" in result.stderr
    assert not output.exists()


def test_bundle_rename_refuses_a_tag_the_app_manifests_do_not_carry(tmp_path: Path) -> None:
    """The build job renames bundles first, so the mismatch is caught there too."""
    result = subprocess.run(
        ["node", str(_REPO / "scripts/rename-bundle-to-tag.mjs"),
         f"v{_bump_patch(_APP_VERSION)}"],
        capture_output=True, text=True, timeout=15, check=False, cwd=tmp_path,
    )

    assert result.returncode != 0
    assert "package.json" in result.stderr
