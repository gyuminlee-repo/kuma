"""Sequence-direct InterProScan domain annotation (EMBL-EBI REST API, stdlib only).

Submits a protein sequence to the EMBL-EBI InterProScan 5 REST service, polls
for completion, and parses integrated InterPro entries whose type is DOMAIN.
Results are cached by SHA-256 of the cleaned sequence under kuma_cache_dir()/domains.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from kuma_core.shared.config_paths import kuma_cache_dir
from kuma_core.shared.net import get_ssl_context

logger = logging.getLogger(__name__)

_IPRSCAN_RUN = "https://www.ebi.ac.uk/Tools/services/rest/iprscan5/run/"
_IPRSCAN_STATUS = "https://www.ebi.ac.uk/Tools/services/rest/iprscan5/status/{job}"
_IPRSCAN_RESULT = "https://www.ebi.ac.uk/Tools/services/rest/iprscan5/result/{job}/json"

# Conservative defaults matching the BLAST polling pattern used elsewhere.
_DEFAULT_POLL_INTERVAL: float = 10.0   # seconds between status checks
_DEFAULT_MAX_POLL_SECONDS: float = 540.0  # 9 minutes, leaves margin under the 660s client timeout

# Standard 20 AAs + extended IUPAC protein codes (ambiguity codes included).
# Gap ("-") and stop ("*") are intentionally excluded: they break the 1-based
# reference-frame contract. A single trailing stop is stripped before this check.
_VALID_AA_RE = re.compile(r"^[ACDEFGHIKLMNPQRSTVWYacdefghiklmnpqrstvwyXxBbZzJjUuOo]+$")

_CACHE_DIR_NAME = "domains"

# Callable accepted as a progress hook: (percent: int, message: str) -> None
ProgressCallback = Callable[[int, str], None]


# ---------------------------------------------------------------------------
# Sequence validation
# ---------------------------------------------------------------------------


def _validate_sequence(seq: str) -> str:
    """Strip FASTA headers, collapse whitespace, validate AA alphabet.

    Returns the cleaned, uppercased sequence without trailing stop codons.
    Raises ValueError on empty, too-short, too-long, or invalid sequences.
    """
    lines = seq.strip().splitlines()
    aa_lines = [ln.strip() for ln in lines if not ln.startswith(">")]
    clean = "".join(aa_lines).replace(" ", "").replace("\t", "").rstrip("*")

    if not clean:
        raise ValueError("Protein sequence is empty")
    if len(clean) < 10:
        raise ValueError(
            f"Protein sequence too short ({len(clean)} aa; minimum 10 required)"
        )
    if len(clean) > 40_000:
        raise ValueError(
            f"Protein sequence too long ({len(clean)} aa; maximum 40 000)"
        )
    if not _VALID_AA_RE.match(clean):
        invalid = sorted(
            {c for c in clean if not _VALID_AA_RE.match(c)},
        )
        raise ValueError(f"Invalid amino acid characters: {invalid}")

    return clean.upper()


def _seq_sha256(seq: str) -> str:
    """SHA-256 hex digest of a clean (already uppercased, no stop) sequence."""
    return hashlib.sha256(seq.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def _cache_path(seq_hash: str) -> Path:
    d = kuma_cache_dir() / _CACHE_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{seq_hash}.json"


def _load_cache(seq_hash: str) -> Optional[list[dict]]:
    p = _cache_path(seq_hash)
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except Exception as exc:  # noqa: BLE001
            logger.warning("Domain cache read failed for %s: %s", seq_hash[:8], exc)
    return None


def _save_cache(seq_hash: str, domains: list[dict]) -> None:
    try:
        _cache_path(seq_hash).write_text(
            json.dumps(domains, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Domain cache write failed for %s: %s", seq_hash[:8], exc)


# ---------------------------------------------------------------------------
# InterProScan JSON parsing
# ---------------------------------------------------------------------------


def _parse_iprscan_json(data: dict) -> list[dict]:
    """Parse an InterProScan result payload; return deduplicated DOMAIN entries.

    Only integrated InterPro entries (``signature.entry`` present) with
    ``type == "DOMAIN"`` are included.  Deduplication key: (ipr_accession,
    start, end).  Results are sorted ascending by start position.
    """
    seen: set[tuple[str, int, int]] = set()
    domains: list[dict] = []

    if not isinstance(data, dict):
        return []
    for result in data.get("results", []):
        for match in result.get("matches", []):
            sig = match.get("signature") or {}
            entry = sig.get("entry")

            # Require an integrated InterPro entry of type DOMAIN.
            if not entry:
                continue
            if (entry.get("type") or "").upper() != "DOMAIN":
                continue

            ipr_acc: str = entry.get("accession") or ""
            ipr_name: str = entry.get("name") or ""

            # Prefer the library name from signatureLibraryRelease.
            lib_release = sig.get("signatureLibraryRelease") or {}
            db: str = lib_release.get("library") or ""

            for loc in match.get("locations") or []:
                try:
                    start = int(loc.get("start") or 0)
                    end = int(loc.get("end") or 0)
                except (TypeError, ValueError):
                    continue
                if start <= 0 or end <= 0 or start > end:
                    continue

                key = (ipr_acc, start, end)
                if key in seen:
                    continue
                seen.add(key)

                entry_dict: dict = {
                    "id": ipr_acc,
                    "name": ipr_name or ipr_acc,
                    "start": start,
                    "end": end,
                    "db": db or "InterPro",
                }

                domains.append(entry_dict)

    domains.sort(key=lambda d: d["start"])
    return domains


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_interproscan(
    sequence: str,
    email: str,
    *,
    progress: Optional[ProgressCallback] = None,
    poll_interval: float = _DEFAULT_POLL_INTERVAL,
    max_poll_seconds: float = _DEFAULT_MAX_POLL_SECONDS,
) -> tuple[list[dict], bool, str]:
    """Submit *sequence* to InterProScan and return parsed DOMAIN entries.

    Parameters
    ----------
    sequence:
        Raw protein sequence string (FASTA headers stripped automatically).
        Validated and uppercased before submission.
    email:
        Contact email required by EBI REST API terms of use.
    progress:
        Optional callback invoked with (percent: int, message: str) at key
        milestones.  ``percent`` is in [0, 100].
    poll_interval:
        Seconds to wait between status polls.
    max_poll_seconds:
        Hard timeout for the poll loop; raises ValueError on expiry.

    Returns
    -------
    (domains, cache_hit, ref_hash)
        domains    — list of domain dicts; empty if none found.
        cache_hit  — True if the result was served from cache (no network).
        ref_hash   — SHA-256 hex of the cleaned sequence (stable across calls).
    """
    seq = _validate_sequence(sequence)
    ref_hash = _seq_sha256(seq)

    # --- Cache check ---
    cached = _load_cache(ref_hash)
    if cached is not None:
        logger.info("Domain cache hit: %s… (len=%d)", ref_hash[:8], len(seq))
        if progress:
            progress(100, "cache_hit")
        return cached, True, ref_hash

    ssl_ctx = get_ssl_context()

    if progress:
        progress(5, "submitting")

    # --- Submit job ---
    fasta = f">query\n{seq}\n"
    post_data = urllib.parse.urlencode({
        "email": email,
        "sequence": fasta,
        "stype": "p",
        "goterms": "false",
        "pathways": "false",
    }).encode()

    try:
        submit_req = urllib.request.Request(_IPRSCAN_RUN, data=post_data, method="POST")
        with urllib.request.urlopen(submit_req, context=ssl_ctx, timeout=30) as resp:
            job_id = resp.read().decode().strip()
    except Exception as exc:
        raise ValueError(f"InterProScan submission failed: {exc}") from exc

    if not job_id:
        raise ValueError("InterProScan returned an empty job ID")

    if progress:
        progress(10, f"submitted:{job_id}")

    # --- Poll status ---
    deadline = time.monotonic() + max_poll_seconds
    status_text = ""

    while time.monotonic() < deadline:
        time.sleep(poll_interval)

        try:
            status_url = _IPRSCAN_STATUS.format(job=job_id)
            with urllib.request.urlopen(
                urllib.request.Request(status_url),
                context=ssl_ctx,
                timeout=15,
            ) as resp:
                status_text = resp.read().decode().strip()
        except Exception as exc:
            logger.debug("InterProScan status poll failed: %s", exc)
            continue

        if status_text == "FINISHED":
            break
        if status_text in ("FAILURE", "ERROR", "NOT_FOUND"):
            raise ValueError(f"InterProScan job {job_id} failed: {status_text}")

        elapsed = time.monotonic() - (deadline - max_poll_seconds)
        if progress:
            pct = min(90, 10 + int(elapsed / max(max_poll_seconds, 1) * 80))
            progress(pct, f"running:{status_text}")
    else:
        raise ValueError(
            f"InterProScan timed out after {max_poll_seconds:.0f}s "
            f"(last status: {status_text or 'UNKNOWN'})"
        )

    if progress:
        progress(92, "fetching_result")

    # --- Fetch result ---
    try:
        result_url = _IPRSCAN_RESULT.format(job=job_id)
        with urllib.request.urlopen(
            urllib.request.Request(result_url, headers={"Accept": "application/json"}),
            context=ssl_ctx,
            timeout=30,
        ) as resp:
            result_data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise ValueError(
            f"InterProScan result fetch failed for {job_id}: {exc}"
        ) from exc

    if progress:
        progress(96, "parsing")

    domains = _parse_iprscan_json(result_data)
    if domains:
        _save_cache(ref_hash, domains)

    if progress:
        progress(100, "done")

    return domains, False, ref_hash
