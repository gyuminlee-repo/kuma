"""Vendor integrity tests use inert text files; no executable or network runs."""
import hashlib
import importlib.util
import io
import os
import shutil
import tarfile
from pathlib import Path
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]

# The linux-x64 slot is reusable only when its POSIX owner-execute bit is set.
# Windows derives that bit from the file extension and chmod cannot set it.
posix_mode_only = pytest.mark.skipif(
    os.name == "nt", reason="POSIX executable mode bit on the linux-x64 slot"
)


@pytest.fixture
def vendor(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("vendor_minimap2_audit", ROOT / "python-core/scripts/vendor-minimap2.py")
    assert spec is not None, "vendor script must have an importable module spec"
    loader = spec.loader
    assert loader is not None, "vendor script must have a source loader"
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    monkeypatch.setattr(module, "vendor_dir", lambda: tmp_path / "vendor")
    archive = tmp_path / "fixture.tar.bz2"
    binary = b"inert reviewed vendor fixture"
    with tarfile.open(archive, "w:bz2") as output:
        member = tarfile.TarInfo(f"minimap2-{module.MINIMAP2_VERSION}_x64-linux/minimap2")
        member.size = len(binary)
        output.addfile(member, io.BytesIO(binary))
    monkeypatch.setattr(module, "ARCHIVE_SHA256", {"linux-x64": hashlib.sha256(archive.read_bytes()).hexdigest()}, raising=False)
    monkeypatch.setattr(module, "BINARY_SHA256", {"linux-x64": hashlib.sha256(binary).hexdigest()}, raising=False)
    monkeypatch.setattr(module, "download_with_progress", lambda _url, dest: shutil.copyfile(archive, dest))
    probe = Mock(return_value=(True, "2.30-r1287"))
    monkeypatch.setattr(module, "check_version", probe)
    return module, probe, binary


def test_changed_download_is_refused_before_probe_and_preserves_existing(vendor, tmp_path, monkeypatch):
    module, probe, _ = vendor
    dest = module.vendor_dir() / "linux-x64/minimap2"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"existing unverified fixture")
    monkeypatch.setattr(module, "ARCHIVE_SHA256", {"linux-x64": "0" * 64}, raising=False)
    with pytest.raises(RuntimeError, match="SHA256"):
        module.install_linux_x64()
    probe.assert_not_called()
    assert dest.read_bytes() == b"existing unverified fixture"


def test_existing_vendor_binary_is_compared_to_verified_archive_before_execution(vendor):
    module, probe, binary = vendor
    dest = module.vendor_dir() / "linux-x64/minimap2"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"untrusted stale fixture")
    def checked(path):
        assert path.read_bytes() == binary
        return True, "2.30-r1287"
    probe.side_effect = checked
    module.install_linux_x64()
    assert dest.read_bytes() == binary
    probe.assert_called_once()


@posix_mode_only
def test_verified_matching_binary_is_reused_without_execution(vendor):
    module, probe, binary = vendor
    dest = module.vendor_dir() / "linux-x64/minimap2"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(binary)
    dest.chmod(0o700)
    module.install_linux_x64()
    probe.assert_not_called()
    assert dest.read_bytes() == binary


@posix_mode_only
def test_verified_matching_binary_is_reused_without_network(vendor, monkeypatch):
    module, probe, binary = vendor
    dest = module.vendor_dir() / "linux-x64/minimap2"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(binary)
    dest.chmod(0o700)

    def refuse_download(url, _dest):
        pytest.fail(f"reusing a pinned binary must not download {url}")

    monkeypatch.setattr(module, "download_with_progress", refuse_download)
    module.install_linux_x64()
    probe.assert_not_called()
    assert dest.read_bytes() == binary
    assert list(dest.parent.iterdir()) == [dest]


def test_extracted_binary_that_differs_from_its_pin_is_refused(vendor, monkeypatch):
    module, probe, _ = vendor
    monkeypatch.setattr(module, "BINARY_SHA256", {"linux-x64": "0" * 64})
    dest = module.vendor_dir() / "linux-x64/minimap2"
    with pytest.raises(RuntimeError, match="pinned binary"):
        module.install_linux_x64()
    probe.assert_not_called()
    assert not dest.exists()


def test_preplaced_platform_status_does_not_execute_unverified_file(vendor):
    module, probe, _ = vendor
    dest = module.vendor_dir() / "windows-x64/minimap2.exe"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"inert unknown fixture")
    module.skip_platform("windows-x64", "fixture")
    probe.assert_not_called()


@posix_mode_only
def test_matching_binary_without_executable_mode_is_repaired(vendor):
    module, probe, binary = vendor
    dest = module.vendor_dir() / "linux-x64/minimap2"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(binary)
    dest.chmod(0o600)
    module.install_linux_x64()
    assert dest.read_bytes() == binary
    assert dest.stat().st_mode & module.stat.S_IXUSR
    probe.assert_called_once()
