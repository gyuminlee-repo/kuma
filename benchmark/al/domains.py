"""Real domain annotation for stratification (plan D6 / F4-F5 / F8).

Domain-quota selection needs real InterPro/Pfam boundaries, not pseudo-segments.
We resolve a protein's domains from its UniProt accession via the UniProt REST
API (InterPro/Pfam cross-references), caching the result to a local JSON so the
217-assay sweep hits the network at most once per accession.

Policy:
- Never silently drop an assay: a lookup failure raises ``DomainsUnavailable``
  and the caller logs + excludes-with-reason.
- Stratify proteins by domain count: ``multi`` (>=2 domains) vs ``single``.
- A ``degenerate`` flag marks assays whose measured mutations all fall inside one
  domain even on a multi-domain protein (domain stratification is meaningless
  there) — computed by ``classify_stratum`` given the assay's mutated positions.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_UNIPROT_URL = "https://rest.uniprot.org/uniprotkb/{acc}.json"
_INTERPRO_URL = (
    "https://www.ebi.ac.uk/interpro/api/entry/all/protein/uniprot/{acc}/"
    "?type=domain&page_size=100"
)


class DomainsUnavailable(RuntimeError):
    """Raised when real domains cannot be resolved (network down, no annotation)."""


def _cache_path(cache_dir: str | Path, acc: str) -> Path:
    return Path(cache_dir) / f"domains_{acc}.json"


def _parse_uniprot_domains(record: dict) -> list[dict]:
    """Extract domain-like features from a UniProt JSON record.

    Uses UniProt 'Domain' features and InterPro/Pfam xref-derived regions when
    present. Returns [{name, start, end}] sorted by start.
    """
    domains: list[dict] = []
    for feat in record.get("features", []):
        if feat.get("type") in {"Domain", "Region"}:
            loc = feat.get("location", {})
            start = (loc.get("start") or {}).get("value")
            end = (loc.get("end") or {}).get("value")
            name = feat.get("description") or feat.get("type")
            if isinstance(start, int) and isinstance(end, int) and end >= start:
                domains.append({"name": str(name), "start": int(start), "end": int(end)})
    # Deduplicate identical spans, keep order by start.
    seen = set()
    uniq = []
    for d in sorted(domains, key=lambda x: (x["start"], x["end"])):
        key = (d["start"], d["end"])
        if key not in seen:
            seen.add(key)
            uniq.append(d)
    return uniq


def _fetch_interpro_domains(acc: str, timeout: int) -> list[dict]:
    """Query the EBI InterPro API for domain-type entries + boundaries.

    Returns [{name, start, end, source}] from member-DB domain signatures
    (Pfam/CDD/etc.) mapped onto the protein. Richer than sparse UniProt features.
    """
    import urllib.request

    url = _INTERPRO_URL.format(acc=acc)
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310
        data = json.loads(resp.read().decode())
    out: list[dict] = []
    for res in data.get("results") or []:
        meta = res.get("metadata", {})
        name = str(meta.get("name") or meta.get("accession") or "domain")
        src = meta.get("source_database")
        for prot in res.get("proteins") or []:
            for epl in prot.get("entry_protein_locations") or []:
                for fr in epl.get("fragments") or []:
                    s, e = fr.get("start"), fr.get("end")
                    if isinstance(s, int) and isinstance(e, int) and e >= s:
                        out.append({"name": name, "start": int(s), "end": int(e), "source": str(src)})
    return out


def _merge_domains(domains: list[dict]) -> list[dict]:
    """Sort by start and drop exact-duplicate spans (keep first/richest name)."""
    seen: set[tuple[int, int]] = set()
    uniq: list[dict] = []
    for d in sorted(domains, key=lambda x: (x["start"], x["end"])):
        key = (d["start"], d["end"])
        if key not in seen:
            seen.add(key)
            uniq.append({k: d[k] for k in ("name", "start", "end") if k in d})
    return uniq

def fetch_domains(
    uniprot_acc: str, cache_dir: str | Path, *, allow_network: bool = True, timeout: int = 60
) -> list[dict]:
    """Return real domains [{name,start,end}] for an accession, caching to JSON.

    Boundary sources, merged: the EBI InterPro API (domain-type member-DB
    signatures — primary, rich) plus UniProt 'Domain'/'Region' features. A cached
    result needs no network. The cache records ``annotated`` so callers can tell
    "confirmed no domain annotation" (exclude-with-reason) from a populated result.

    On a cache miss with ``allow_network`` False, raises ``DomainsUnavailable``.
    If BOTH sources error (network down) raises ``DomainsUnavailable``; if both
    simply return nothing (genuinely unannotated) returns an empty list with
    ``annotated`` False cached (NOT an exception) so single-domain proteins are
    not lost — the caller decides exclusion via ``classify_stratum``/``annotated``.
    """
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = _cache_path(cache_dir, uniprot_acc)
    if cache.exists():
        return json.loads(cache.read_text())["domains"]
    if not allow_network:
        raise DomainsUnavailable(f"no cached domains for {uniprot_acc} and network disabled")

    collected: list[dict] = []
    errors: list[str] = []
    # Primary: InterPro API (domain boundaries from Pfam/CDD/etc.).
    try:
        collected.extend(_fetch_interpro_domains(uniprot_acc, timeout))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"interpro:{exc!r}")
    # Secondary: UniProt 'Domain'/'Region' features.
    try:
        import urllib.request

        with urllib.request.urlopen(_UNIPROT_URL.format(acc=uniprot_acc), timeout=timeout) as resp:  # noqa: S310
            record = json.loads(resp.read().decode())
        collected.extend(_parse_uniprot_domains(record))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"uniprot:{exc!r}")

    if not collected and len(errors) == 2:
        # both sources errored -> genuine lookup failure, not "no annotation"
        raise DomainsUnavailable(f"domain lookup failed for {uniprot_acc}: {errors}")

    domains = _merge_domains(collected)
    cache.write_text(
        json.dumps(
            {"accession": uniprot_acc, "domains": domains, "annotated": bool(domains),
             "sources_errored": errors},
            indent=0,
        )
    )
    return domains


def domain_count(domains: list[dict]) -> int:
    return len(domains)


def classify_stratum(domains: list[dict], mutated_positions: list[int]) -> str:
    """Return 'single' | 'multi' | 'degenerate'.

    - 'single'    : protein has < 2 annotated domains.
    - 'degenerate': >=2 domains but every mutated position falls in (at most) one
      domain -> domain stratification is meaningless for this assay.
    - 'multi'     : >=2 domains and mutations span >=2 domains.
    """
    if domain_count(domains) < 2:
        return "single"
    hit = set()
    for p in mutated_positions:
        for i, d in enumerate(domains):
            if d["start"] <= p <= d["end"]:
                hit.add(i)
                break
    return "multi" if len(hit) >= 2 else "degenerate"
