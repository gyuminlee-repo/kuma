"""Shared constants for MAME activity parsing and normalization."""

from __future__ import annotations

import re

# Covers both 'WT_1' and 'WT1' variants found in real data (spec §11-B).
WT_PATTERN = re.compile(r"^WT_?\d+$")
