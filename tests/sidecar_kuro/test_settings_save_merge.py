# ruff: noqa: S101
"""settings_save must not replace preferences.json with defaults.

The UI keeps the bundle it loaded and ships it back on every change. When
settings_load failed (sidecar still starting, a result it could not validate),
the UI holds an empty bundle, and the first change after that sends only the
field that changed. Writing that payload as the whole file reset every other
preference to its default: the contact email disappeared, withdrawn consents
came back on, offline mode went off. The save merges what the caller stated
over what the file already holds instead.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_SIDECAR_DIR = _PROJECT_ROOT / "python-core"
if str(_SIDECAR_DIR) not in sys.path:
    sys.path.insert(0, str(_SIDECAR_DIR))

from sidecar_kuro.handlers import settings as _settings  # noqa: E402

_STORED = {
    "language": "en",
    "theme": "light",
    "default_workspace_folder": None,
    "network": {
        "offline_mode": True,
        "consent_uniprot": False,
        "consent_blast": True,
        "consent_alphafold": True,
        "consent_interpro": True,
        "consent_esmfold": False,
        "contact_email": "someone@lab.org",
    },
}


@pytest.fixture()
def prefs(tmp_path, monkeypatch):
    path = tmp_path / "preferences.json"
    path.write_text(json.dumps(_STORED), encoding="utf-8")
    monkeypatch.setenv("KUMA_PREFERENCES_PATH", str(path))
    return path


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_partial_bundle_keeps_every_other_stored_preference(prefs):
    # What the UI sends after a failed load: {} plus the one changed field.
    _settings.handle_save({"settings": {"theme": "dark"}})
    saved = _read(prefs)
    assert saved["theme"] == "dark"
    assert saved["network"] == _STORED["network"]


def test_partial_network_section_keeps_sibling_network_fields(prefs):
    _settings.handle_save({"settings": {"network": {"offline_mode": False}}})
    saved = _read(prefs)
    assert saved["network"]["offline_mode"] is False
    assert saved["network"]["contact_email"] == "someone@lab.org"
    assert saved["network"]["consent_uniprot"] is False
    assert saved["network"]["consent_esmfold"] is False


def test_an_explicit_empty_email_still_clears_it(prefs):
    _settings.handle_save({"settings": {"network": {"contact_email": ""}}})
    assert _read(prefs)["network"]["contact_email"] == ""


def test_full_bundle_is_written_as_given(prefs):
    full = json.loads(json.dumps(_STORED))
    full["theme"] = "auto"
    full["network"]["consent_uniprot"] = True
    _settings.handle_save({"settings": full})
    assert _read(prefs) == full


def test_unreadable_file_is_replaced_by_the_payload(prefs):
    prefs.write_text("{not json", encoding="utf-8")
    _settings.handle_save({"settings": {"theme": "dark"}})
    saved = _read(prefs)
    assert saved["theme"] == "dark"
    assert saved["network"]["contact_email"] == ""


def test_missing_file_is_created_from_the_payload(tmp_path, monkeypatch):
    path = tmp_path / "nested" / "preferences.json"
    monkeypatch.setenv("KUMA_PREFERENCES_PATH", str(path))
    _settings.handle_save({"settings": {"network": {"contact_email": "a@b.org"}}})
    saved = _read(path)
    assert saved["network"]["contact_email"] == "a@b.org"
    assert saved["theme"] == "auto"
