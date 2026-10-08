# ruff: noqa: S101
"""EBI Job Dispatcher submissions need the user's own contact email.

EBI asks every submitter for a real address so it can reach whoever is
overloading its queue, and blocks addresses it cannot reach. A shared
placeholder therefore put every install behind one address EBI could block for
all of them. With no address configured the sidecar must not submit at all and
must say so with ``error_code == "contact_email_required"`` so the UI can ask.

Network is mocked throughout: a submission is detected by the URL it would hit.
"""
from __future__ import annotations

import io
import json
import sys
import urllib.parse
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_SIDECAR_DIR = _PROJECT_ROOT / "python-core"
if str(_SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(_SIDECAR_DIR))

import sidecar_kuro.core as _core  # noqa: E402
from sidecar_kuro.handlers import external as _ext  # noqa: E402

_SEQ = "MKTAYIAKQRQISFVKSHFSRQLEERLGLIEVQAPILSRVGDGTQDNLSGAEKAVQVKVK"
_BLAST_RUN = "/ncbiblast/run"
_IPRSCAN_RUN = "/iprscan5/run"


@pytest.fixture()
def no_email(tmp_path, monkeypatch):
    """Every source of a contact email is empty."""
    monkeypatch.delenv("KURO_CONTACT_EMAIL", raising=False)
    monkeypatch.setenv("KUMA_PREFERENCES_PATH", str(tmp_path / "preferences.json"))
    monkeypatch.setattr(_core, "_CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(_core, "_config_cache", None)
    return tmp_path


class _Recorder:
    """Stands in for urlopen: records every request, answers like EBI."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, bytes | None]] = []

    def __call__(self, req, *args, **kwargs):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        data = getattr(req, "data", None)
        self.calls.append((url, data))
        if url.endswith(_BLAST_RUN) or _IPRSCAN_RUN in url:
            return io.BytesIO(b"job-1")
        if "/status/" in url:
            return io.BytesIO(b"FINISHED")
        if "/ncbiblast/result/" in url:
            return io.BytesIO(json.dumps({"hits": []}).encode())
        if "/iprscan5/result/" in url:
            return io.BytesIO(json.dumps({"results": [{"matches": []}]}).encode())
        return io.BytesIO(b"{}")

    def submissions(self, marker: str) -> list[bytes | None]:
        return [data for url, data in self.calls if marker in url]


@pytest.fixture()
def net(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr("urllib.request.urlopen", rec)
    monkeypatch.setattr("time.sleep", lambda *_a, **_k: None)
    return rec


def _search(**overrides):
    params = {
        "gene_name": "",
        "organism": "",
        "translation": _SEQ,
        "known_accession": "",
        "use_blast": True,
    }
    params.update(overrides)
    return _ext.handle_search_uniprot(params)


def _submitted_email(data: bytes | None) -> str:
    assert data is not None
    return urllib.parse.parse_qs(data.decode())["email"][0]


# ── BLAST ───────────────────────────────────────────────────────────────


def test_blast_without_email_is_not_submitted(no_email, net):
    result = _search()
    assert net.submissions(_BLAST_RUN) == [], "BLAST was submitted with no contact email"
    assert result["error_code"] == "contact_email_required"
    # The skip is not an error in the search itself: the other lookups still ran
    # and their outcome is reported the usual way.
    assert not (result.get("error_detail") or "").startswith("BLAST")


def test_blast_uses_the_email_saved_in_settings(no_email, net):
    (no_email / "preferences.json").write_text(
        json.dumps({"network": {"contact_email": "someone@lab.org"}}), encoding="utf-8")
    result = _search()
    subs = net.submissions(_BLAST_RUN)
    assert len(subs) == 1
    assert _submitted_email(subs[0]) == "someone@lab.org"
    assert result.get("error_code") is None


def test_env_var_still_wins(no_email, net, monkeypatch):
    monkeypatch.setenv("KURO_CONTACT_EMAIL", "env@lab.org")
    (no_email / "preferences.json").write_text(
        json.dumps({"network": {"contact_email": "someone@lab.org"}}), encoding="utf-8")
    _search()
    assert _submitted_email(net.submissions(_BLAST_RUN)[0]) == "env@lab.org"


def test_legacy_config_json_still_works(no_email, net):
    (no_email / "config.json").write_text(
        json.dumps({"contact_email": "legacy@lab.org"}), encoding="utf-8")
    _search()
    assert _submitted_email(net.submissions(_BLAST_RUN)[0]) == "legacy@lab.org"


def test_malformed_email_counts_as_missing(no_email, net):
    (no_email / "preferences.json").write_text(
        json.dumps({"network": {"contact_email": "not-an-address"}}), encoding="utf-8")
    result = _search()
    assert net.submissions(_BLAST_RUN) == []
    assert result["error_code"] == "contact_email_required"


def test_blast_switched_off_asks_for_nothing(no_email, net):
    result = _search(use_blast=False)
    assert net.submissions(_BLAST_RUN) == []
    assert result.get("error_code") is None


# ── InterProScan ────────────────────────────────────────────────────────


def test_interproscan_without_email_is_not_submitted(no_email, net, monkeypatch):
    from kuma_core.kuro import domains as _dom

    monkeypatch.setattr(_dom, "_cache_path", lambda h: no_email / f"{h}.json")
    result = _ext.handle_annotate_domains_by_sequence({"sequence": _SEQ})
    assert net.submissions(_IPRSCAN_RUN) == [], "InterProScan was submitted with no contact email"
    assert result["source"] == "error"
    assert result["error_code"] == "contact_email_required"


def test_interproscan_cache_hit_needs_no_email(no_email, net, monkeypatch):
    """Nothing is submitted on a cache hit, so there is nothing to ask for."""
    import hashlib

    from kuma_core.kuro import domains as _dom

    monkeypatch.setattr(_dom, "_cache_path", lambda h: no_email / f"{h}.json")
    cached = [{"id": "IPR000276", "name": "GPCR", "start": 5, "end": 50, "db": "PFAM"}]
    ref_hash = hashlib.sha256(_SEQ.encode()).hexdigest()
    (no_email / f"{ref_hash}.json").write_text(json.dumps(cached))

    result = _ext.handle_annotate_domains_by_sequence({"sequence": _SEQ})
    assert net.calls == []
    assert result["source"] == "interproscan"
    assert result["cache_hit"] is True
    assert result.get("error_code") is None


def test_interproscan_uses_the_email_saved_in_settings(no_email, net, monkeypatch):
    from kuma_core.kuro import domains as _dom

    monkeypatch.setattr(_dom, "_cache_path", lambda h: no_email / f"{h}.json")
    (no_email / "preferences.json").write_text(
        json.dumps({"network": {"contact_email": "someone@lab.org"}}), encoding="utf-8")
    _ext.handle_annotate_domains_by_sequence({"sequence": _SEQ})
    subs = net.submissions(_IPRSCAN_RUN)
    assert len(subs) == 1
    assert _submitted_email(subs[0]) == "someone@lab.org"


def test_no_placeholder_address_left_in_the_sidecar():
    source = (_SIDECAR_DIR / "sidecar_kuro" / "core.py").read_text(encoding="utf-8")
    assert "example.com" not in source


# ── Candidate order and what Settings is told ─────────────────────────────


def test_malformed_env_value_falls_through_to_settings(no_email, net, monkeypatch):
    """A typo in the environment must not hide a valid address the user saved."""
    monkeypatch.setenv("KURO_CONTACT_EMAIL", "not-an-address")
    (no_email / "preferences.json").write_text(
        json.dumps({"network": {"contact_email": "someone@lab.org"}}), encoding="utf-8")
    result = _search()
    subs = net.submissions(_BLAST_RUN)
    assert len(subs) == 1
    assert _submitted_email(subs[0]) == "someone@lab.org"
    assert result.get("error_code") is None


def test_malformed_settings_value_falls_through_to_legacy_config(no_email, net):
    (no_email / "preferences.json").write_text(
        json.dumps({"network": {"contact_email": "not-an-address"}}), encoding="utf-8")
    (no_email / "config.json").write_text(
        json.dumps({"contact_email": "legacy@lab.org"}), encoding="utf-8")
    _search()
    assert _submitted_email(net.submissions(_BLAST_RUN)[0]) == "legacy@lab.org"


def _load_response() -> dict:
    from sidecar_kuro.handlers import settings as _settings

    return _settings.handle_load({})


@pytest.mark.parametrize(
    ("env", "prefs", "legacy", "expected_email", "expected_source"),
    [
        ("env@lab.org", "someone@lab.org", "", "env@lab.org", "env"),
        ("", "someone@lab.org", "legacy@lab.org", "someone@lab.org", "preferences"),
        ("", "", "legacy@lab.org", "legacy@lab.org", "legacy_config"),
        ("bad", "bad", "", None, "none"),
        ("", "", "", None, "none"),
    ],
)
def test_settings_load_reports_the_address_submissions_will_use(
    no_email, monkeypatch, env, prefs, legacy, expected_email, expected_source,
):
    """Settings shows the address EBI gets and where it came from.

    An address from the environment or the legacy config file was used for
    every submission while the Settings field sat empty, so the user could not
    see what was being sent nor that the field would be overridden.
    """
    if env:
        monkeypatch.setenv("KURO_CONTACT_EMAIL", env)
    (no_email / "preferences.json").write_text(
        json.dumps({"network": {"contact_email": prefs}}), encoding="utf-8")
    if legacy:
        (no_email / "config.json").write_text(
            json.dumps({"contact_email": legacy}), encoding="utf-8")
    response = _load_response()
    assert response["effective_contact_email"] == expected_email
    assert response["contact_email_source"] == expected_source
    assert _core._get_contact_email() == expected_email


def test_docstring_names_the_legacy_config_path_the_code_reads():
    source = (_SIDECAR_DIR / "sidecar_kuro" / "core.py").read_text(encoding="utf-8")
    assert "~/.kuro/config.json" not in source
    assert _core._CONFIG_PATH.parts[-3:] == (".kuma", "kuro", "config.json")
    assert "~/.kuma/kuro/config.json" in source
