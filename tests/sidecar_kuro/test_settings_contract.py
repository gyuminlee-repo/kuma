"""Every settings field must declare whether anything acts on it.

A control that stores a preference and changes no behaviour is a promise the app
does not keep. That is the defect behind the 17mers: the fill-on-failure box read
as a gate, the request carried `auto_relax: true` regardless, and the relax pass
took two nt off a floor the user had typed. Auditing the settings dialog for the
same shape turned up five more, none of which any test would have noticed.

So the contract is written down here rather than inferred. Every field of the
settings bundle is either WIRED, naming the file that acts on it and a string
that proves the file still does, or INERT, naming why not. A new field belongs to
neither until someone puts it in one, and this test fails until they do.

An inference-based version of this check was tried first and dropped: matching
field names across the tree scored 5 wrong out of 13 on a labelled corpus. It
missed `consent_*` (the consumer builds the key as a template literal, so the
name never appears literally) and it accepted `language` and `theme` on hits from
unrelated code that happens to use those very ordinary words.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from sidecar_kuro.models import SettingsBundle

REPO = Path(__file__).resolve().parents[2]
DIALOG = REPO / "src" / "components" / "layout" / "SettingsDialog.tsx"

# field -> (file that acts on it, a string that file must still contain)
WIRED: dict[str, tuple[str, str]] = {
    "theme": ("src/store/slices/settingsSlice.ts", "mapThemeFromBundle"),
    "offline_mode": ("src/store/slices/settingsSlice.ts", "setOfflineMode"),
    "consent_uniprot": ("src/store/slices/networkConsentSlice.ts", "isNetworkServiceEnabled"),
    "consent_blast": ("src/store/slices/diversitySlice.ts", 'isNetworkServiceEnabled("blast")'),
    "consent_alphafold": ("src/store/slices/diversitySlice.ts", 'requireNetworkConsent("alphafold")'),
    "consent_interpro": ("src/store/slices/diversitySlice.ts", 'requireNetworkConsent("interpro")'),
    "persist_on_cancel": (
        "python-core/sidecar_kuro/handlers/design.py",
        'persist_on_cancel == "partial"',
    ),
}

# field -> why nothing acts on it. Move an entry to WIRED when that changes.
INERT: dict[str, str] = {
    # Dormant model fields rather than broken controls: no dialog control writes
    # either one, so neither states anything to a user. The language picker in
    # Settings does work; it drives i18next and its own localStorage key, and
    # never touches this field. Disabling that picker would be the wrong reading
    # of this entry.
    "language": "no control writes it and loadSettings never applies it",
    "default_workspace_folder": "nothing reads or writes it anywhere in the tree",
    "concurrency_default": "designs run one mutation at a time; no parallel job pool exists",
    "cancel_timeout_secs": "graceful_kill callers pass a literal 2 s and no Rust code reads the bundle",
    "crash_log_auto_send": "nothing sends crash reports",
    "anonymous_stats": "nothing sends usage data",
}


def _bundle_fields() -> set[str]:
    """Leaf field names of the settings bundle, nested sections flattened."""
    names: set[str] = set()
    for name, field in SettingsBundle.model_fields.items():
        annotation = field.annotation
        nested = getattr(annotation, "model_fields", None)
        if nested:
            names.update(nested)
        else:
            names.add(name)
    return names


def test_every_settings_field_is_declared_wired_or_inert():
    declared = set(WIRED) | set(INERT)
    actual = _bundle_fields()
    undeclared = actual - declared
    stale = declared - actual
    assert not undeclared, (
        "settings fields with no declaration: "
        f"{sorted(undeclared)}. Add each to WIRED with the file that acts on it, "
        "or to INERT with the reason nothing does."
    )
    assert not stale, f"declared fields that no longer exist in the bundle: {sorted(stale)}"


def test_wired_and_inert_do_not_overlap():
    assert not (set(WIRED) & set(INERT))


@pytest.mark.parametrize("field", sorted(WIRED))
def test_wired_field_still_has_its_consumer(field: str):
    rel, evidence = WIRED[field]
    path = REPO / rel
    assert path.is_file(), f"{field}: declared consumer {rel} does not exist"
    assert evidence in path.read_text(encoding="utf-8"), (
        f"{field}: {rel} no longer contains {evidence!r}. Either the consumer moved "
        "(update the entry) or the field went inert (move it to INERT)."
    )


# The subset of INERT that has a control in the dialog. The others are dormant
# model fields with no control, so there is nothing to disable and nothing to
# label; only these have to match what the dialog switches off.
INERT_WITH_A_CONTROL = {
    "concurrency_default",
    "cancel_timeout_secs",
    "crash_log_auto_send",
    "anonymous_stats",
}


def test_inert_fields_are_the_ones_the_dialog_disables():
    """The dialog and this file must name the same set, or one of them is lying."""
    source = DIALOG.read_text(encoding="utf-8")
    match = re.search(r"export const INACTIVE_SETTINGS = \[(.*?)\] as const;", source, re.S)
    assert match, "INACTIVE_SETTINGS not found in SettingsDialog.tsx"
    listed = set(re.findall(r'"([a-z_]+)"', match.group(1)))
    assert INERT_WITH_A_CONTROL <= set(INERT), (
        "a field cannot be disabled as inactive and declared wired at the same time"
    )
    assert listed == INERT_WITH_A_CONTROL, (
        f"dialog disables {sorted(listed)} but this file expects "
        f"{sorted(INERT_WITH_A_CONTROL)}"
    )


def test_disabled_controls_carry_the_inactive_notice():
    """Disabling without saying why reads as a bug rather than as a statement."""
    source = DIALOG.read_text(encoding="utf-8")
    assert source.count('t("settings.inactiveHint")') == len(INERT_WITH_A_CONTROL), (
        "every disabled control needs the notice next to it; disabling one without "
        "saying why reads as a bug"
    )
    assert source.count("disabled\n") >= len(INERT_WITH_A_CONTROL)
