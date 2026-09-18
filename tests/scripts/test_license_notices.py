"""License collection regression tests with installed-metadata fixtures."""
from email.message import Message
import importlib.util
from pathlib import Path
import subprocess
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("license_collector", ROOT / "scripts/collect-python-licenses.py")
assert SPEC and SPEC.loader
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


class Distribution:
    def __init__(self, root, name, requires=(), license_text="Copyright example\nPermission granted\n"):
        self.metadata = Message()
        self.metadata["Name"] = name
        self.metadata["License-Expression"] = "MIT"
        self.version = "1.0"
        self.requires = list(requires)
        self.root = root / name
        self.root.mkdir()
        self.files = [Path(f"{name}.dist-info/licenses/LICENSE.txt")]
        target = self.root / self.files[0]
        target.parent.mkdir(parents=True)
        target.write_text(license_text, encoding="utf8")

    def locate_file(self, path):
        return self.root / path


def test_transitive_dependencies_and_packaging_roles(tmp_path):
    dists = {name: Distribution(tmp_path, name, reqs) for name, reqs in {
        "appdep": ["certifi", "child[feature]"], "certifi": [],
        "child": ['extra-child; extra == "feature"', 'windows; sys_platform == "win32"'],
        "extra-child": [], "builder": ["child"],
    }.items()}
    records = collector.collect({"runtime": ["appdep"], "packaging": ["builder"]}, dists.__getitem__, {"sys_platform": "linux"})
    by_name = {r["name"]: r for r in records}
    assert set(by_name) == set(dists)
    assert by_name["child"]["roles"] == ["packaging", "runtime"]
    assert by_name["extra-child"]["roles"] == ["runtime"]
    assert "Copyright example" in collector.render(records)
    assert len(by_name["certifi"]["files"][0]["sha256"]) == 64


def test_later_extra_revisits_a_distribution(tmp_path):
    dists = {name: Distribution(tmp_path, name, reqs) for name, reqs in {
        "a": ["common"], "b": ["common[optional]"],
        "common": ['leaf; extra == "optional"'], "leaf": [],
    }.items()}
    records = collector.collect({"runtime": ["a", "b"]}, dists.__getitem__)
    assert {r["name"] for r in records} == set(dists)


def test_cycles_are_finite(tmp_path):
    dists = {"a": Distribution(tmp_path, "a", ["b"]), "b": Distribution(tmp_path, "b", ["a"])}
    assert len(collector.collect({"runtime": ["a"]}, dists.__getitem__)) == 2


def test_missing_empty_and_identifier_only_license_fail(tmp_path):
    dist = Distribution(tmp_path, "example")
    dist.files = []
    dist.metadata["License"] = "MIT"
    with pytest.raises(ValueError, match="No license text"):
        collector.legal_files(dist)
    dist.files = [Path("missing-LICENSE.txt")]
    # No matching legal filename is still no license evidence.
    with pytest.raises(ValueError, match="No license text"):
        collector.legal_files(dist)
    dist.files = [Path("LICENSE")]
    with pytest.raises(FileNotFoundError):
        collector.legal_files(dist)
    (dist.root / "LICENSE").write_text("\n")
    with pytest.raises(ValueError, match="Empty legal file"):
        collector.legal_files(dist)


def test_nonstandard_pep639_license_file_is_retained(tmp_path):
    dist = Distribution(tmp_path, "example")
    extra = Path("example.dist-info/licenses/native-component.txt")
    (dist.root / extra).write_text("Native component attribution")
    dist.files.append(extra)
    assert len(collector.legal_files(dist)) == 2


def test_installed_version_must_satisfy_declared_requirement(tmp_path):
    dist = Distribution(tmp_path, "example")
    with pytest.raises(ValueError, match="does not satisfy"):
        collector.collect({"runtime": ["example>=2"]}, lambda name: dist)
    with pytest.raises(ValueError, match="empty"):
        collector.collect({"runtime": []}, lambda name: dist)


def test_node_collectors():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node notice tests also run explicitly in license-evidence CI")
    subprocess.run([node, "--test", "scripts/tests/license-notices.test.mjs"], cwd=ROOT, check=True)


def test_edlib_supplement_is_version_bound_and_preserves_provenance(tmp_path):
    dist = Distribution(tmp_path, "edlib")
    dist.version = "1.3.9.post1"
    dist.files = []
    files = collector.legal_files(dist)
    assert "2014 Martin Šošić" in files[0]["text"]
    assert "git/blobs/" in files[0]["source"]
    dist.version = "999.0"
    with pytest.raises(ValueError, match="No license text"):
        collector.legal_files(dist)
    dist.version = "1.3.9.post1"
    dist.metadata.replace_header("License-Expression", "Apache-2.0")
    with pytest.raises(ValueError, match="Invalid version-bound"):
        collector.legal_files(dist)


def test_about_displays_project_license_not_legacy_internal_use():
    source = (ROOT / "src/components/layout/SharedAboutDialog.tsx").read_text(encoding="utf8")
    assert "GNU GPL v2" in source
    assert 't("about.licenseText")' not in source
