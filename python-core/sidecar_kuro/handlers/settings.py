"""Handlers for settings_load and settings_save RPC methods.

Preferences are stored at $KUMA_PREFERENCES_PATH (env override) or
~/.kuma/preferences.json.  Writes use an atomic tmp-file + os.replace
pattern so a crash mid-write never leaves a corrupt file.
"""

import json
import logging
import os
import tempfile
from pathlib import Path

from sidecar_kuro.models import (
    SettingsBundle,
    SettingsLoadRequest,
    SettingsLoadResponse,
    SettingsSaveRequest,
    SettingsSaveResponse,
)

logger = logging.getLogger(__name__)


def _preferences_path() -> Path:
    """Resolve the preferences file path.

    Priority: KUMA_PREFERENCES_PATH env var -> ~/.kuma/preferences.json
    """
    env_path = os.environ.get("KUMA_PREFERENCES_PATH")
    if env_path:
        return Path(env_path)
    return Path.home() / ".kuma" / "preferences.json"


def load_bundle() -> SettingsBundle:
    """Read the stored preferences, falling back to defaults.

    Shared with handlers that have to act on a preference rather than merely
    hand it to the UI. A preference no handler reads is a control that stores
    something and changes nothing, which is the failure this exists to avoid.
    """
    prefs_path = _preferences_path()

    if prefs_path.exists():
        try:
            raw = prefs_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            return SettingsBundle(**data)
        except Exception as exc:
            logger.warning(
                "Failed to parse preferences at %s: %s -- returning defaults",
                prefs_path,
                exc,
            )

    return SettingsBundle()


def handle_load(params: dict) -> dict:
    """Load preferences from disk; return defaults if file is absent or unreadable."""
    SettingsLoadRequest(**params)  # validate (empty body)
    # Imported here: core reads load_bundle from this module at call time.
    from sidecar_kuro.core import resolve_contact_email

    email, source = resolve_contact_email()
    return SettingsLoadResponse(
        settings=load_bundle(),
        effective_contact_email=email,
        contact_email_source=source,
    ).model_dump()


def _merge(base: dict, update: dict) -> dict:
    """Overlay ``update`` onto ``base``, descending into nested sections."""
    merged = dict(base)
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _stored_preferences(prefs_path: Path) -> dict:
    """The file as it stands, or ``{}`` when it is absent or unusable."""
    try:
        data = json.loads(prefs_path.read_text(encoding="utf-8"))
        SettingsBundle(**data)
    except FileNotFoundError:
        return {}
    except Exception as exc:
        logger.warning("Ignoring unreadable preferences at %s: %s", prefs_path, exc)
        return {}
    return data if isinstance(data, dict) else {}


def handle_save(params: dict) -> dict:
    """Persist preferences to disk using an atomic write.

    Only the fields the caller actually sent replace stored values. The UI ships
    back the bundle it loaded, but when settings_load failed it holds an empty
    bundle, so its next save carries just the one field that changed. Writing
    that as the whole file reset every other preference (contact email, the
    consents, offline mode) to its default.
    """
    req = SettingsSaveRequest(**params)

    prefs_path = _preferences_path()
    prefs_path.parent.mkdir(parents=True, exist_ok=True)

    merged = _merge(
        _stored_preferences(prefs_path),
        req.settings.model_dump(exclude_unset=True),
    )
    payload = SettingsBundle(**merged).model_dump()
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)

    # Atomic write: write to a sibling tmp file, then rename.
    tmp_fd, tmp_name = tempfile.mkstemp(
        dir=str(prefs_path.parent), suffix=".tmp", prefix="preferences_"
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
            fh.write(serialized)
        os.replace(tmp_name, str(prefs_path))
    except OSError as exc:
        logger.error("Atomic write failed for %s: %s", prefs_path, exc)
        try:
            os.unlink(tmp_name)
        except OSError as unlink_exc:
            logger.warning("Could not clean up tmp file %s: %s", tmp_name, unlink_exc)
        raise

    return SettingsSaveResponse(ok=True, path=str(prefs_path)).model_dump()
