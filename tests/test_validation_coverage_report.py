"""The evidence gate must distinguish passed, skipped, failed and absent tests."""
from __future__ import annotations

from pathlib import Path
import runpy
import xml.etree.ElementTree as ET

import pytest

REPORT = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/report_validation_coverage.py"))
summarize = REPORT["summarize"]
gate_passes = REPORT["gate_passes"]
EXPECTED = {("tests.external", "test_alpha"), ("tests.external", "test_beta")}


def _xml(tmp_path, entries):
    root = ET.Element("testsuites")
    suite = ET.SubElement(root, "testsuite")
    for name, status in entries:
        case = ET.SubElement(suite, "testcase", classname="tests.external", name=name)
        if status != "passed":
            ET.SubElement(case, status)
    path = tmp_path / "report.xml"
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return path


def test_pass_requires_actual_testcase_evidence(tmp_path):
    report = summarize(_xml(tmp_path, [("test_alpha", "passed"), ("test_beta", "passed")]), EXPECTED)
    assert report["all_executed_and_passed"]
    assert gate_passes(report, require_executed=True)


def test_default_ci_reports_skips_without_claiming_validation(tmp_path):
    report = summarize(_xml(tmp_path, [("test_alpha", "skipped"), ("test_beta", "skipped")]), EXPECTED)
    assert report["counts"] == {"passed": 0, "skipped": 2, "failed": 0, "missing": 0}
    assert not report["all_executed_and_passed"]
    assert gate_passes(report)
    assert not gate_passes(report, require_executed=True)


@pytest.mark.parametrize("status", ["failure", "error"])
def test_failures_fail_both_modes(tmp_path, status):
    report = summarize(_xml(tmp_path, [("test_alpha", status), ("test_beta", "passed")]), EXPECTED)
    assert not gate_passes(report)
    assert not gate_passes(report, require_executed=True)


def test_omitted_test_is_not_silently_counted_as_a_skip(tmp_path):
    report = summarize(_xml(tmp_path, [("test_alpha", "passed")]), EXPECTED)
    assert report["counts"]["missing"] == 1
    assert not gate_passes(report)


def test_partial_parameterization_does_not_claim_all_executed(tmp_path):
    report = summarize(_xml(tmp_path, [("test_alpha[one]", "passed"), ("test_alpha[two]", "skipped"), ("test_beta", "passed")]), EXPECTED)
    assert report["counts"]["skipped"] == 1
    assert not gate_passes(report, require_executed=True)


def test_unrelated_synthetic_test_does_not_fill_a_missing_external_test(tmp_path):
    report = summarize(_xml(tmp_path, [("test_synthetic", "passed")]), EXPECTED)
    assert report["counts"]["missing"] == 2


def test_empty_inventory_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="empty"):
        summarize(_xml(tmp_path, []), set())


def test_invalid_xml_is_an_error(tmp_path):
    path = tmp_path / "broken.xml"
    path.write_text("<not-closed>", encoding="utf-8")
    with pytest.raises(ET.ParseError):
        summarize(path, EXPECTED)


def test_inventory_is_discovered_without_importing_or_running_private_tests():
    root = Path(__file__).resolve().parents[1]
    expected = REPORT["discover_expected"](root)
    assert ("tests.integration.test_xlsx_pipeline", "test_scenario_a_plate_layout") in expected
    assert any(module.endswith("TestReferenceGroundTruth") for module, _name in expected)
    assert not any("test_label_swap_from_temporary_workbooks" in name for _module, name in expected)


def test_missing_source_cannot_be_certified(tmp_path):
    with pytest.raises(OSError):
        REPORT["discover_expected"](tmp_path)
