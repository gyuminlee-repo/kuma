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


def handle_load(params: dict) -> dict:
    """Load preferences from disk; return defaults if file is absent or unreadable."""
    SettingsLoadRequest(**params)  # validate (empty body)

    prefs_path = _preferences_path()
    bundle = SettingsBundle()

    if prefs_path.exists():
        try:
            raw = prefs_path.read_text(encoding="utf-8")
            data = json.loads(raw)
            bundle = SettingsBundle(**data)
        except Exception as exc:
            logger.warning(
                "Failed to parse preferences at %s: %s -- returning defaults",
                prefs_path,
                exc,
            )

    return SettingsLoadResponse(settings=bundle).model_dump()


def handle_save(params: dict) -> dict:
    """Persist preferences to disk using an atomic write."""
    req = SettingsSaveRequest(**params)

    prefs_path = _preferences_path()
    prefs_path.parent.mkdir(parents=True, exist_ok=True)

    payload = req.settings.model_dump()
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
