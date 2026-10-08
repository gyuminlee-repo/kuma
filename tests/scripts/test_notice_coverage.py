"""scripts/check-notice-coverage.py: shipped components versus NOTICE inputs."""
import importlib.util
import json
import re
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("notice_coverage", ROOT / "scripts/check-notice-coverage.py")
assert SPEC and SPEC.loader
coverage = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(coverage)

# Names copied from the v0.16.66 linux-kuro TOC (bare) and win-kuro TOC (tabbed).
LINUX_TOC = "\n".join([
    "libpython3.12.so.1.0", "libssl.so.3", "libffi.so.8",
    "numpy.libs/libquadmath-2284e583-a9307bba.so.0.0.0",
    "numpy.libs/libscipy_openblas64_-f48b354e.so", "certifi/cacert.pem",
])
WIN_TOC = "PYZ\t0\txlwt\nPYZ\t0\txlrd\nb\t6945272\tpython312.dll\nb\t1\tnumpy.libs\\msvcp140-a4c2.dll\n"


def write_inputs(tmp_path, packages, headings):
    notice = tmp_path / "NOTICE-python.json"
    notice.write_text(json.dumps({"packages": [
        {"name": name, "files": [{"text": text}]} for name, text in packages.items()
    ]}), encoding="utf8")
    bundled = tmp_path / "NOTICE-bundled.md"
    bundled.write_text("## Bundled Binaries\n\n" + "".join(f"### {h}\n\ntext\n\n" for h in headings), encoding="utf8")
    return notice, bundled


def run(monkeypatch, tmp_path, toc_text, packages, headings, *flags):
    toc = tmp_path / "toc.txt"
    toc.write_text(toc_text, encoding="utf8")
    notice, bundled = write_inputs(tmp_path, packages, headings)
    monkeypatch.setattr(coverage.metadata, "packages_distributions", lambda: {})
    monkeypatch.setattr(sys, "argv", ["x", "--notice-json", str(notice), "--bundled", str(bundled), *flags, str(toc)])
    return coverage.main()


FULL_NUMPY = "OpenBLAS ... libgfortran ... libquadmath"
ALL_HEADINGS = ["CPython", "OpenSSL", "libffi", "Microsoft Visual C++ runtime"]


def test_missing_python_and_native_notices_fail(monkeypatch, tmp_path, capsys):
    # v0.16.66 state: no numpy, certifi or runtime notices at all.
    assert run(monkeypatch, tmp_path, LINUX_TOC, {}, []) == 1
    out = capsys.readouterr().out
    for component in ("numpy / libquadmath", "numpy / OpenBLAS", "certifi", "CPython", "OpenSSL", "libffi"):
        assert f"MISSING  {component} [" in out


def test_everything_covered_passes(monkeypatch, tmp_path):
    packages = {"numpy": FULL_NUMPY, "certifi": "MPL", "xlrd": "BSD", "xlwt": "BSD"}
    assert run(monkeypatch, tmp_path, LINUX_TOC, packages, ALL_HEADINGS) == 0
    assert run(monkeypatch, tmp_path, WIN_TOC, packages, ALL_HEADINGS) == 0


def test_dist_present_but_marker_absent_is_missing(monkeypatch, tmp_path, capsys):
    packages = {"numpy": "OpenBLAS only", "certifi": "MPL"}
    assert run(monkeypatch, tmp_path, LINUX_TOC, packages, ALL_HEADINGS) == 1
    out = capsys.readouterr().out
    assert "MISSING  numpy / libquadmath [" in out
    assert "MISSING  numpy / OpenBLAS [" not in out


def test_tabbed_pyz_listing_and_backslashes(monkeypatch, tmp_path, capsys):
    assert run(monkeypatch, tmp_path, WIN_TOC, {"xlrd": "BSD"}, []) == 1
    out = capsys.readouterr().out
    assert "MISSING  xlwt [" in out
    assert "MISSING  CPython [" in out
    assert "MISSING  Microsoft Visual C++ / UCRT runtime [" in out
    assert "ok       xlrd [" in out


def test_heading_substring_does_not_count(monkeypatch, tmp_path, capsys):
    # "### CPython notes" is not a CPython heading, and body text never counts.
    assert run(monkeypatch, tmp_path, "python312.dll\n", {}, ["CPython notes"]) == 1
    assert "MISSING  CPython [" in capsys.readouterr().out


def test_warn_only_reports_but_exits_zero(monkeypatch, tmp_path, capsys):
    assert run(monkeypatch, tmp_path, LINUX_TOC, {}, [], "--warn-only") == 0
    assert "MISSING  OpenSSL [" in capsys.readouterr().out


def test_generic_layer_maps_top_level_package_to_distribution(monkeypatch, tmp_path, capsys):
    toc = tmp_path / "toc.txt"
    toc.write_text("PYZ\t0\tsomepkg.sub\nkuma_core/x.py\n", encoding="utf8")
    notice, bundled = write_inputs(tmp_path, {}, [])
    monkeypatch.setattr(coverage.metadata, "packages_distributions",
                        lambda: {"somepkg": ["Some-Pkg"], "kuma_core": ["kuma"]})
    monkeypatch.setattr(sys, "argv", ["x", "--notice-json", str(notice), "--bundled", str(bundled), str(toc)])
    assert coverage.main() == 1
    out = capsys.readouterr().out
    assert "MISSING  Some-Pkg [" in out
    assert "kuma [" not in out  # the project itself is not a third-party notice


@pytest.mark.parametrize("name", ["libreadline.so.8", "libsslfoo", "numpyx/y.py"])
def test_unrelated_names_match_no_rule(name):
    matched = [c for c, pattern, _ in coverage.RULES if re.search(pattern, name)]
    assert matched == [], (name, matched)
