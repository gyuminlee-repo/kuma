"""UniProt feature annotation fetch utilities.

Provides ``fetch_active_site_features`` which returns Active site and Binding
site positions directly in the accession (UniProt) frame.  No biopython, no
alignment — positions come straight from the UniProt JSON response.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request as _urllib_req

from kuma_core.shared.net import get_ssl_context

logger = logging.getLogger(__name__)

_UNIPROT_API = "https://rest.uniprot.org/uniprotkb/{accession}?format=json"


def fetch_active_site_features(accession: str) -> dict:
    """Return Active site and Binding site positions for *accession*.

    Positions are in the accession (UniProt) frame — location.start.value from
    the UniProt JSON response.  No ref_seq round-trip or alignment is applied.

    Returns a dict::

        {
          "accession": str,
          "active_site_positions": list[int],   # sorted, 1-based
          "binding_positions": list[int],        # sorted, 1-based
          "source": "uniprot" | "none" | "error",
          "has_annotation": bool,
        }

    On network or parse failure returns has_annotation=False, source='error' or
    'none'.
    """
    accession = accession.strip().upper()
    if not re.match(r"^[A-Za-z0-9]{1,20}$", accession):
        return {
            "accession": accession,
            "active_site_positions": [],
            "binding_positions": [],
            "source": "error",
            "has_annotation": False,
        }

    url = _UNIPROT_API.format(accession=accession)
    try:
        req = _urllib_req.Request(url, headers={"Accept": "application/json"})
        with _urllib_req.urlopen(req, context=get_ssl_context(), timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("UniProt features fetch failed for %s: %s", accession, exc)
        return {
            "accession": accession,
            "active_site_positions": [],
            "binding_positions": [],
            "source": "error",
            "has_annotation": False,
        }

    features = data.get("features", []) if isinstance(data, dict) else []
    active_site_positions: list[int] = []
    binding_positions: list[int] = []

    for feat in features:
        feat_type = feat.get("type", "")
        try:
            pos = int(feat.get("location", {}).get("start", {}).get("value", 0))
        except (TypeError, ValueError):
            continue
        if pos <= 0:
            continue
        if feat_type == "Active site":
            active_site_positions.append(pos)
        elif feat_type == "Binding site":
            binding_positions.append(pos)

    active_site_positions = sorted(set(active_site_positions))
    binding_positions = sorted(set(binding_positions))
    has_annotation = bool(active_site_positions or binding_positions)
    source = "uniprot" if has_annotation else "none"

    return {
        "accession": accession,
        "active_site_positions": active_site_positions,
        "binding_positions": binding_positions,
        "source": source,
        "has_annotation": has_annotation,
    }
