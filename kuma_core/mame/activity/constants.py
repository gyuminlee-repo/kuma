"""Shared constants for MAME activity parsing and normalization."""

from __future__ import annotations

import re

# One contract shared by detection and every activity reader.
WT_PATTERN = re.compile(r"^WT(?:_?\d+)?$", re.IGNORECASE)
