"""Tests for SUBUNIT extraction and oligomeric classification (biological unit Tier 1)."""

from sidecar_kuro.handlers.external import _classify_oligomeric, _extract_subunit


def _entry(*values):
    return {"comments": [{"commentType": "SUBUNIT", "texts": [{"value": v} for v in values]}]}


def test_homodimer_is_multimer():
    sub = _extract_subunit(_entry("Homodimer."))
    assert sub == "Homodimer."
    assert _classify_oligomeric(sub) == "multimer"


def test_heterotetramer_is_multimer():
    sub = _extract_subunit(_entry("Heterotetramer of two alpha chains and two beta chains."))
    assert _classify_oligomeric(sub) == "multimer"


def test_monomer():
    sub = _extract_subunit(_entry("Monomer (PubMed:123)."))
    assert _classify_oligomeric(sub) == "monomer"


def test_microbial_infection_only_returns_text_but_unknown():
    sub = _extract_subunit(_entry("(Microbial infection) Interacts with host factor X."))
    assert sub == "(Microbial infection) Interacts with host factor X."
    assert _classify_oligomeric(sub) == "unknown"


def test_microbial_infection_skipped_when_real_subunit_present():
    sub = _extract_subunit(_entry("(Microbial infection) Interacts with host X.", "Homotrimer."))
    assert sub == "Homotrimer."
    assert _classify_oligomeric(sub) == "multimer"


def test_oligomer_keyword_is_multimer():
    assert _classify_oligomeric("Forms an oligomer.") == "multimer"


def test_no_comments_returns_none_and_unknown():
    assert _extract_subunit({"comments": []}) is None
    assert _extract_subunit({}) is None
    assert _classify_oligomeric(None) == "unknown"
