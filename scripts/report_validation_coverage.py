"""Report whether the known external-data test scopes actually executed.

Read a pytest JUnit report, not environment-variable presence. The external
scopes below are deliberately explicit; expected test functions are discovered
from their AST so a deleted/renamed scope or an omitted test is not a green
zero. Synthetic tests in the same files are NOT counted as external evidence.

Normal CI allows documented skips and exposes them in its summary/artifact.
--require-executed turns missing, failed, or skipped evidence into a failed gate
for an authorized private-data validation run. No data is fetched or published.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

# (source, class or None, function prefix). These identify the existing tests,
# not a claim of independent ground truth. The read suite checks self-consistency.
EXTERNAL_SCOPES = (
    ("tests/integration/test_xlsx_pipeline.py", None, "test_scenario_"),
    ("tests/mame/test_well_consensus_regression.py", "TestReferenceGroundTruth", "test_"),
    ("tests/mame/test_plate_order_check.py", None, "test_the_260722_export_"),
)


def discover_expected(repo_root: Path) -> set[tuple[str, str]]:
    expected: set[tuple[str, str]] = set()
    for source, class_name, prefix in EXTERNAL_SCOPES:
        tree = ast.parse((repo_root / source).read_text(encoding="utf-8"), filename=source)
        module = source.removesuffix(".py").replace("/", ".")
        nodes = tree.body
        if class_name is not None:
            classes = [node for node in nodes if isinstance(node, ast.ClassDef) and node.name == class_name]
            if len(classes) != 1:
                raise ValueError(f"External validation scope missing or duplicated: {source}:{class_name}")
            nodes = classes[0].body
            module += "." + class_name
        names = [node.name for node in nodes
                 if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(prefix)]
        if not names:
            raise ValueError(f"External validation scope contains no tests: {source}:{class_name or prefix}")
        expected.update((module, name) for name in names)
    return expected


def summarize(junit_path: Path, expected: set[tuple[str, str]]) -> dict:
    if not expected:
        raise ValueError("Cannot certify an empty external-test inventory")
    root = ET.parse(junit_path).getroot()
    if root.tag not in {"testsuite", "testsuites"}:
        raise ValueError("Expected a JUnit testsuite or testsuites document")
    evidence: dict[tuple[str, str], list[str]] = {key: [] for key in expected}
    for case in root.iter("testcase"):
        key = (case.get("classname", ""), case.get("name", "").split("[", 1)[0])
        if key not in evidence:
            continue
        if case.find("failure") is not None or case.find("error") is not None:
            status = "failed"
        elif case.find("skipped") is not None:
            status = "skipped"
        else:
            status = "passed"
        evidence[key].append(status)
    rows = []
    for (module, name), outcomes in sorted(evidence.items()):
        status = (
            "missing" if not outcomes else
            "failed" if "failed" in outcomes else
            "skipped" if "skipped" in outcomes else "passed"
        )
        rows.append({"test": f"{module}.{name}", "status": status,
                     "instances": len(outcomes), "outcomes": outcomes})
    counts = {status: sum(row["status"] == status for row in rows)
              for status in ("passed", "skipped", "failed", "missing")}
    return {
        "schema_version": 1,
        "scope": "existing_external_data_tests",
        "expected_test_functions": len(expected),
        "counts": counts,
        "all_executed_and_passed": counts["passed"] == len(expected),
        "scope_note": "Execution evidence for the explicitly inventoried external-data scopes only. The external-read suite checks self-consistency, not independent biological ground truth. Synthetic contracts and samtools equivalence are separate evidence.",
        "tests": rows,
    }


def gate_passes(report: dict, *, require_executed: bool = False) -> bool:
    counts = report["counts"]
    return counts["failed"] == 0 and counts["missing"] == 0 and (
        not require_executed or report["all_executed_and_passed"]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--junit", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--require-executed", action="store_true",
                        help="Fail unless every expected external test executed and passed")
    args = parser.parse_args(argv)
    try:
        report = summarize(args.junit, discover_expected(args.repo_root))
    except (OSError, ValueError, SyntaxError, ET.ParseError) as exc:
        print(f"External validation evidence unavailable: {exc}", file=sys.stderr)
        return 1
    text = json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    counts = report["counts"]
    summary = (
        "## External-data validation coverage\n\n"
        f"Expected functions: {report['expected_test_functions']}; "
        f"passed: {counts['passed']}; skipped: {counts['skipped']}; "
        f"failed: {counts['failed']}; missing: {counts['missing']}.\n\n"
        + ("All inventoried tests executed and passed.\n" if report["all_executed_and_passed"]
           else "**External-data validation is NOT complete on this run.**\n")
        + "\n" + report["scope_note"] + "\n"
    )
    print(summary)
    for row in report["tests"]:
        print(f"{row['status']:7} {row['test']}")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as stream:
            stream.write(summary)
    return 0 if gate_passes(report, require_executed=args.require_executed) else 1


if __name__ == "__main__":
    raise SystemExit(main())
