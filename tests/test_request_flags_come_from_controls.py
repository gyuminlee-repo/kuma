"""A request flag must carry what its control says, not a constant.

This is the exact shape of the 17mer defect. `fillOnFailure` was read, stored,
restored and rendered, so every consumer check said it was wired. The request
went out with `auto_relax: true` regardless, and the sidecar relax pass it turned
on lowered the primer length floor by two, under a box the user had unchecked.

A dead-control sweep cannot see this: the control has consumers. What gives it
away is a boolean or numeric literal in a request payload, so that is what this
checks. Snake_case keys only, since those are the wire format; a camelCase field
is local state. Numeric matching follows `send*Request` payload construction
rather than every object literal, because response initializers are not outgoing
requests.

The detector was scored on the labelled corpus in CORPUS below before being
trusted, per the rule that a pattern matcher is wrong until measured. It has to
pass the bare literal and clear the guarded-spread form the diversity flags use,
because a flag inside `...(enabled && { flag: true })` is already conditioned on
its toggle and writing it as a variable would change nothing.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

LITERAL = re.compile(
    r"^\s*([a-z][a-z0-9]*(?:_[a-z0-9]+)+):\s*"
    r"(true|false|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*,?\s*$"
)
SPREAD_OPEN = re.compile(r"\.\.\.\(.*&&\s*\{\s*$")
REQUEST_OPEN = re.compile(r"\bsend\w*Request\s*(?:<[^>]+>)?\s*\(")

SCANNED_PREFIXES = ("src/store/", "src/lib/", "src/components/")

# Occurrences that are not request flags. Each needs a reason, because the point
# is to make someone look rather than to let the list grow.
ALLOWED: dict[str, str] = {
    "src/lib/mame/sampleData.ts:is_fallback": (
        "sample rows handed to the table for the demo run, not a request payload"
    ),
    # mapq_threshold now follows rawRunParams.mapqThreshold. trim_flank_bp stays
    # pinned at 30: AnalyzeRawRunParams consumes it as bases around each aligned
    # hit in per-well FASTA slices, and analyze forwards it to ingest_run_folder.
    "src/store/mame/slices/inputSlice.ts:trim_flank_bp": (
        "real raw-run flank-trim parameter pinned to the sidecar's slice margin"
    ),
}


def _flagged(text: str) -> list[tuple[int, str]]:
    """Snake_case booleans, plus numeric literals inside request payloads."""
    found: list[tuple[int, str]] = []
    guard_depths: list[int] = []
    request_depths: list[int] = []
    request_waiting_for_payload = False
    depth = 0
    for lineno, line in enumerate(text.splitlines(), 1):
        if REQUEST_OPEN.search(line):
            request_waiting_for_payload = True
        if request_waiting_for_payload and "{" in line:
            request_depths.append(depth + 1)
            request_waiting_for_payload = False
        if SPREAD_OPEN.search(line):
            guard_depths.append(depth + line.count("{") - line.count("}"))
        match = LITERAL.match(line)
        is_boolean = match and match.group(2) in {"true", "false"}
        if match and not guard_depths and (is_boolean or request_depths):
            found.append((lineno, match.group(1)))
        depth += line.count("{") - line.count("}")
        while guard_depths and depth < guard_depths[-1]:
            guard_depths.pop()
        while request_depths and depth < request_depths[-1]:
            request_depths.pop()
    return found


CORPUS: list[tuple[str, str, list[str]]] = [
    (
        "the original defect",
        "return {\n  tol_max: tolMax,\n  auto_relax: true,\n};",
        ["auto_relax"],
    ),
    (
        "guarded spread, the correct form",
        "return {\n  ...(usePipeline && domainDiversityEnabled && {\n"
        "    domain_diversity: true,\n  }),\n};",
        [],
    ),
    (
        "numeric request literal",
        'sendRequest("analyze", {\n  mapq_threshold: 25,\n});',
        ["mapq_threshold"],
    ),
    (
        "guarded numeric literal, the correct form",
        'sendRequest("analyze", {\n'
        "  ...(useDefaultTrim && {\n    trim_flank_bp: 30,\n  }),\n});",
        [],
    ),
    (
        "numeric field driven by its control",
        'sendRequest("analyze", {\n  mapq_threshold: mapqThreshold,\n});',
        [],
    ),
    (
        "numeric local state is not a request payload",
        "const defaults = {\n  mapq_threshold: 25,\n};",
        [],
    ),
    (
        "closed request does not leak its scope",
        'sendRequest("health_info", {});\nconst defaults = {\n  mapq_threshold: 25,\n};',
        [],
    ),
    (
        "flag driven by its control",
        "return {\n  auto_relax: fillOnFailure,\n};",
        [],
    ),
    (
        "literal after the guard closes",
        "return {\n  ...(cond && {\n    inner_flag: true,\n  }),\n  outer_flag: false,\n};",
        ["outer_flag"],
    ),
    (
        "camelCase local state is not a request field",
        "const state = {\n  isDesigning: true,\n};",
        [],
    ),
    (
        "response initializer is not a request payload",
        # The scan is deliberately limited to request construction. This is a
        # sidecar response initializer, so its zero values must not be flagged.
        "export const EMPTY_RESCUE_STATS: RescueStats = {\n"
        "  pool_cascade: 0,\n"
        "  auto_relax: 0,\n"
        "  positions_attempted: 0,\n"
        "  pool_variants_tried: 0,\n"
        "};",
        [],
    ),
]


@pytest.mark.parametrize(
    "source,expected",
    [(source, expected) for _, source, expected in CORPUS],
    ids=[label for label, _, _ in CORPUS],
)
def test_detector_scores_the_corpus(source: str, expected: list[str]):
    assert [name for _, name in _flagged(source)] == expected


def _sources() -> list[str]:
    listing = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    return [
        rel
        for rel in listing
        if rel.startswith(SCANNED_PREFIXES)
        and rel.endswith((".ts", ".tsx"))
        and ".test." not in rel
    ]


def test_no_request_flag_is_pinned_to_a_literal():
    offenders = []
    for rel in _sources():
        for lineno, name in _flagged((REPO / rel).read_text(encoding="utf-8")):
            if f"{rel}:{name}" in ALLOWED:
                continue
            offenders.append(f"{rel}:{lineno} {name}")
    assert not offenders, (
        "request flags pinned to a constant, so whatever control names them "
        f"cannot turn them off: {offenders}. Drive each from its control, or add "
        "it to ALLOWED with the reason it is not a request flag."
    )


def test_allowlist_entries_still_exist():
    """A stale exemption is an exemption nobody has looked at."""
    present = {
        f"{rel}:{name}"
        for rel in _sources()
        for _, name in _flagged((REPO / rel).read_text(encoding="utf-8"))
    }
    assert set(ALLOWED) <= present, (
        f"allowlisted occurrences that no longer exist: {sorted(set(ALLOWED) - present)}"
    )
