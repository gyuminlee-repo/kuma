"""Counts that sit under the wrong amino acid are reported, not raised.

V26 compared the global codon sets, so swapping one entry between two amino
acids kept every codon present and passed the check. The recomputation two
steps later indexes each group by codon name, so the misgrouped table raised
``KeyError: 'AAA'`` instead of returning the validation report the dialog
renders.
"""
from __future__ import annotations

import copy

from kuma_core.kuro.codon_import import validate_codon_table_data

from tests.test_codon_import import _base_table


def _swapped() -> dict:
    data = copy.deepcopy(_base_table())
    lys = data["counts"]["K"]
    asn = data["counts"]["N"]
    entry = next(e for e in lys if e[0] == "AAA")
    lys.remove(entry)
    asn.append(entry)
    return data


def test_control_table_is_valid() -> None:
    report = validate_codon_table_data(copy.deepcopy(_base_table()), "lab_strain")
    assert report.ok, report.error_codes


def test_misgrouped_counts_report_v26() -> None:
    data = _swapped()
    all_codons = sorted(c for group in data["counts"].values() for c, _ in group)
    base_codons = sorted(
        c for group in _base_table()["counts"].values() for c, _ in group
    )
    assert all_codons == base_codons, "the global codon set must stay intact"

    report = validate_codon_table_data(data, "lab_strain")
    assert not report.ok
    assert "V26" in report.error_codes


def test_duplicate_count_entry_reports_v26() -> None:
    data = copy.deepcopy(_base_table())
    lys = data["counts"]["K"]
    lys.append(next(e for e in lys if e[0] == "AAA"))
    report = validate_codon_table_data(data, "lab_strain")
    assert not report.ok
    assert "V26" in report.error_codes
