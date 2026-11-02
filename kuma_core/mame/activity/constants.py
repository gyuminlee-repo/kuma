"""Shared constants for MAME activity parsing and normalization."""

from __future__ import annotations

import re

# One contract shared by detection and every activity reader.
# The replicate separator is optional and may be "_", "-" or one space
# (WT1, WT_1, WT-1, WT 1): a report that writes every sample "<id>-<rep>"
# writes its WT replicates the same way.
WT_PATTERN = re.compile(r"^WT(?:[ _-]?\d+)?$", re.IGNORECASE)
