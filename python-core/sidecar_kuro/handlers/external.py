"""Handlers: external network calls — UniProt, InterPro, ESM embeddings."""

import json
import logging
import re
import time
import urllib.parse
import urllib.request
from difflib import SequenceMatcher

import sidecar_kuro.core as _core
from sidecar_kuro.core import (
    _get_ssl_ctx,
    _get_contact_email,
    _progress,
    logger,
)
from sidecar_kuro.models import (
    AnnotateDomainsBySequenceParams,
    CheckStructuresParams,
    FetchDomainsParams,
    SearchUniprotParams,
    FetchStructureParams,
    FetchInterfaceParams,
    FetchPdbTextParams,
    FetchActiveSiteParams,
    ComputeDispersionParams,
    PredictStructureEsmfoldParams,
)


def handle_fetch_domains(params: dict) -> dict:
    """Fetch protein domain boundaries from InterPro/Pfam via UniProt accession."""
    p = FetchDomainsParams(**params)
    accession = p.accession.strip()
    if not accession:
        raise ValueError("UniProt accession is required")
    if not re.match(r"^[A-Za-z0-9_-]{1,20}$", accession):
        raise ValueError(f"Invalid UniProt accession format: {accession}")

    # Try Pfam first, then fall back to full InterPro
    endpoints = [
        (
            f"https://www.ebi.ac.uk/interpro/api/entry/pfam/protein/uniprot/{accession}?format=json",
            "pfam",
        ),
        (
            f"https://www.ebi.ac.uk/interpro/api/entry/interpro/protein/uniprot/{accession}?format=json",
            "interpro",
        ),
    ]

    for url, db_label in endpoints:
        try:
            req = urllib.request.Request(
                url,
                headers={"Accept": "application/json"},
            )
            with urllib.request.urlopen(req, context=_get_ssl_ctx(), timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            domains: list[dict] = []
            protein_length = 0

            for entry in data.get("results", []):
                meta = entry.get("metadata", {})
                entry_acc = meta.get("accession", "")
                entry_name = meta.get("name", "")

                for protein in entry.get("proteins", []):
                    prot_len = protein.get("protein_length", 0)
                    if prot_len > protein_length:
                        protein_length = prot_len

                    for loc in protein.get("entry_protein_locations", []):
                        for frag in loc.get("fragments", []):
                            domains.append({
                                "name": entry_name,
                                "id": entry_acc,
                                "start": int(frag["start"]),
                                "end": int(frag["end"]),
                                "db": db_label,
                            })

            if domains:
                domains.sort(key=lambda d: d["start"])
                return {
                    "accession": accession,
                    "domains": domains,
                    "source": "interpro_api",
                    "protein_length": protein_length,
                }
        except Exception as exc:
            logger.debug("Domain fetch from %s failed: %s", db_label, exc)
            continue

    return {
        "accession": accession,
        "domains": [],
        "source": "error",
        "error_msg": f"No domain data found for {accession}",
    }


def _sequence_identity(seq_a: str, seq_b: str) -> float:
    """Calculate percent identity between two protein sequences.

    Strips trailing stop codons (*), then checks for exact or substring
    match before falling back to positional comparison.
    """
    seq_a = seq_a.rstrip("*").strip()
    seq_b = seq_b.rstrip("*").strip()
    if not seq_a or not seq_b:
        return 0.0
    if seq_a == seq_b:
        return 100.0
    # One sequence is a contiguous substring of the other (e.g. signal peptide trimming)
    if seq_a in seq_b or seq_b in seq_a:
        return 100.0
    matches = sum(1 for a, b in zip(seq_a, seq_b) if a == b)
    return round(matches / max(len(seq_a), len(seq_b)) * 100, 1)


def _normalize_organism_name(name: str) -> str:
    """Normalize organism strings for approximate matching."""
    normalized = re.sub(r"[^a-z0-9\s]+", " ", name.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _organism_match_score(query: str, candidate: str) -> tuple[int, float]:
    """Score organism compatibility for candidate ranking.

    Returns a tuple of:
    - discrete priority bucket (higher is better)
    - fuzzy similarity used only as a tie-breaker
    """
    q = _normalize_organism_name(query)
    c = _normalize_organism_name(candidate)
    if not q or not c:
        return (0, 0.0)
    if q == c:
        return (3, 1.0)

    q_tokens = q.split()
    c_tokens = c.split()
    if len(q_tokens) >= 2 and len(c_tokens) >= 2 and q_tokens[:2] == c_tokens[:2]:
        return (2, 1.0)
    if q_tokens and c_tokens and q_tokens[0] == c_tokens[0]:
        return (1, 1.0)

    fuzzy = round(SequenceMatcher(None, q, c).ratio(), 3)
    return (0, fuzzy)


def _candidate_rank_key(query_organism: str, candidate: dict) -> tuple[int, float, float, int]:
    """Rank UniProt candidates by sequence evidence first, organism second."""
    organism_bucket, organism_similarity = _organism_match_score(
        query_organism,
        str(candidate.get("organism", "")),
    )
    return (
        int(round(float(candidate.get("identity", 0.0)) * 10)),
        organism_bucket,
        organism_similarity,
        int(candidate.get("length", 0) or 0),
    )


def _extract_subunit(data: dict) -> str | None:
    """First non-microbial SUBUNIT comment text from a UniProtKB JSON entry."""
    comments = data.get("comments", []) if isinstance(data, dict) else []
    texts = []
    for c in comments:
        if c.get("commentType") == "SUBUNIT":
            for t in c.get("texts", []):
                v = (t.get("value") or "").strip()
                if v:
                    texts.append(v)
    if not texts:
        return None
    for v in texts:
        if not v.lower().startswith("(microbial infection)"):
            return v
    return texts[0]


def _classify_oligomeric(subunit: str | None) -> str:
    """monomer | multimer | unknown from SUBUNIT free text. Multimer wins ties (cautious flag)."""
    if not subunit:
        return "unknown"
    s = subunit.lower()
    if "oligomer" in s or re.search(r"\b(?:homo|hetero)?(?:di|tri|tetra|penta|hexa|hepta|octa|multi)mer", s):
        return "multimer"
    if re.search(r"\bmonomer", s):
        return "monomer"
    return "unknown"


def handle_search_uniprot(params: dict) -> dict:
    """Search UniProt via BLAST (primary) and direct accession lookup (secondary)."""
    p = SearchUniprotParams(**params)
    gene_name = p.gene_name.strip()
    organism = p.organism.strip()
    translation = p.translation.strip()
    known_accession = p.known_accession.strip()

    if not translation and not known_accession:
        raise ValueError("translation or known_accession is required")
    if known_accession and not re.match(r"^[A-Za-z0-9_-]{1,20}$", known_accession):
        raise ValueError(f"Invalid UniProt accession format: {known_accession}")

    candidates: list[dict] = []
    auto_selected: str | None = None
    last_error: str = ""

    def _fetch_json(url: str) -> tuple[dict | None, str]:
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, context=_get_ssl_ctx(), timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8")), ""
        except Exception as exc:
            logger.warning("UniProt fetch failed: %s — %s", url, exc)
            return None, f"{type(exc).__name__}: {exc}"

    def _fetch_text(url: str) -> tuple[str, str]:
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, context=_get_ssl_ctx(), timeout=30) as resp:
                return resp.read().decode("utf-8").strip(), ""
        except Exception as exc:
            return "", f"{type(exc).__name__}: {exc}"

    seen_accessions: set[str] = set()

    if known_accession:
        data, err = _fetch_json(
            f"https://rest.uniprot.org/uniprotkb/{known_accession}?format=json"
        )
        if err:
            last_error = err
        if data and "primaryAccession" in data:
            seq_data = data.get("sequence", {})
            uni_seq = seq_data.get("value", "") if isinstance(seq_data, dict) else ""
            identity = _sequence_identity(translation, uni_seq) if translation else 0.0
            gene_names = [
                gn["geneName"]["value"]
                for gn in data.get("genes", [])
                if gn.get("geneName", {}).get("value")
            ]
            acc = data["primaryAccession"]
            sub = _extract_subunit(data)
            candidates.append({
                "accession": acc,
                "name": ", ".join(gene_names) if gene_names else known_accession,
                "organism": data.get("organism", {}).get("scientificName", ""),
                "length": seq_data.get("length", 0) if isinstance(seq_data, dict) else 0,
                "identity": identity,
                "subunit": sub,
                "oligomeric": _classify_oligomeric(sub),
            })
            seen_accessions.add(acc)
            # Trusted direct accession match with high sequence identity:
            # auto-select immediately and skip slow BLAST submission.
            if identity >= 95.0:
                auto_selected = acc

    if translation and not auto_selected:
        try:
            blast_data = urllib.parse.urlencode({
                "email": _get_contact_email(),
                "program": "blastp",
                "database": "uniprotkb_swissprot",
                "stype": "protein",
                "sequence": translation.rstrip("*"),
            }).encode()
            submit_req = urllib.request.Request(
                "https://www.ebi.ac.uk/Tools/services/rest/ncbiblast/run",
                data=blast_data,
                method="POST",
            )
            with urllib.request.urlopen(submit_req, context=_get_ssl_ctx(), timeout=30) as resp:
                job_id = resp.read().decode().strip()

            status_text = ""
            for _ in range(100):  # was range(20); 100*3s = 300s (5 min) to tolerate EBI queue backlogs
                time.sleep(3)
                status_text, _ = _fetch_text(
                    f"https://www.ebi.ac.uk/Tools/services/rest/ncbiblast/status/{job_id}"
                )
                if status_text == "FINISHED":
                    break
                if status_text in ("FAILURE", "ERROR", "NOT_FOUND"):
                    raise RuntimeError(f"BLAST job failed: {status_text}")
            else:
                # loop exhausted without FINISHED — EBI queue backlog
                raise RuntimeError(f"BLAST timed out after 300s (last status: {status_text or 'UNKNOWN'})")

            if status_text == "FINISHED":
                result_data, err = _fetch_json(
                    f"https://www.ebi.ac.uk/Tools/services/rest/ncbiblast/result/{job_id}/json"
                )
                if err:
                    last_error = err
                if result_data:
                    for hit in result_data.get("hits", [])[:10]:
                        raw_acc = hit.get("hit_acc", "")  # may be "SP:Q50L36" or bare accession
                        acc = raw_acc.split(":")[-1] if ":" in raw_acc else raw_acc
                        if acc in seen_accessions:
                            continue
                        seen_accessions.add(acc)
                        hsps = hit.get("hit_hsps", [])
                        blast_identity = hsps[0].get("hsp_identity", 0.0) if hsps else 0.0
                        hit_def = hit.get("hit_def", "")
                        os_m = re.search(r'\bOS=([^=]+?)(?:\s+\w+=|$)', hit_def)
                        hit_organism = os_m.group(1).strip() if os_m else ""
                        gn_m = re.search(r'\bGN=(\S+)', hit_def)
                        hit_gene = gn_m.group(1) if gn_m else ""
                        hit_len = hsps[0].get("hsp_hit_to", 0) if hsps else 0
                        candidates.append({
                            "accession": acc,
                            "name": hit_gene or acc,
                            "organism": hit_organism,
                            "length": hit_len,
                            "identity": blast_identity,
                        })
        except Exception as exc:
            logger.warning("BLAST search failed: %s", exc)
            last_error = f"BLAST: {type(exc).__name__}: {exc}"

    if gene_name and not auto_selected:
        try:
            search_url = (
                f"https://rest.uniprot.org/uniprotkb/search"
                f"?query=gene_exact%3A{urllib.parse.quote(gene_name)}"
                f"&format=json&size=10"
            )
            text_data, err = _fetch_json(search_url)
            if err:
                last_error = err
            if text_data:
                for entry in text_data.get("results", []):
                    acc = entry.get("primaryAccession", "")
                    if not acc or acc in seen_accessions:
                        continue
                    seen_accessions.add(acc)
                    seq_data = entry.get("sequence", {})
                    uni_seq = seq_data.get("value", "") if isinstance(seq_data, dict) else ""
                    identity = _sequence_identity(translation, uni_seq) if translation else 0.0
                    gene_names = [
                        gn["geneName"]["value"]
                        for gn in entry.get("genes", [])
                        if gn.get("geneName", {}).get("value")
                    ]
                    sub = _extract_subunit(entry)
                    candidates.append({
                        "accession": acc,
                        "name": ", ".join(gene_names) if gene_names else acc,
                        "organism": entry.get("organism", {}).get("scientificName", ""),
                        "length": seq_data.get("length", 0) if isinstance(seq_data, dict) else 0,
                        "identity": identity,
                        "subunit": sub,
                        "oligomeric": _classify_oligomeric(sub),
                    })
        except Exception as exc:
            logger.warning("UniProt text search failed: %s", exc)
            last_error = f"UniProt text search: {type(exc).__name__}: {exc}"

    candidates.sort(key=lambda c: _candidate_rank_key(organism, c), reverse=True)

    if candidates and candidates[0]["identity"] >= 95.0:
        auto_selected = candidates[0]["accession"]

    # Enrich the selected candidate with oligomeric state if missing (one light request).
    sel = auto_selected or (candidates[0]["accession"] if candidates else None)
    if sel:
        for c in candidates:
            if c["accession"] == sel and not c.get("subunit"):
                try:
                    sdata, _e = _fetch_json(
                        f"https://rest.uniprot.org/uniprotkb/{sel}?format=json&fields=cc_subunit"
                    )
                    if sdata:
                        c["subunit"] = _extract_subunit(sdata)
                        c["oligomeric"] = _classify_oligomeric(c.get("subunit"))
                except Exception as exc:
                    logger.warning("SUBUNIT enrich failed for %s: %s", sel, exc)
                break

    return {
        "candidates": candidates,
        "auto_selected": auto_selected,
        "error_detail": last_error or None,
    }


def handle_check_structures_available(params: dict) -> dict:
    """Check AlphaFold availability for a list of UniProt accessions."""
    p = CheckStructuresParams(**params)
    accessions = []
    for raw in p.accessions[:20]:
        acc = raw.strip().upper()
        if acc and re.match(r"^[A-Za-z0-9_-]{1,20}$", acc):
            accessions.append(acc)

    if not accessions:
        return {"availability": {}}

    from concurrent.futures import ThreadPoolExecutor, as_completed
    from kuma_core.kuro.alphafold import check_structure_available

    availability: dict[str, bool] = {}
    with ThreadPoolExecutor(max_workers=min(5, len(accessions))) as ex:
        futures = {ex.submit(check_structure_available, acc): acc for acc in accessions}
        for fut in as_completed(futures):
            acc = futures[fut]
            try:
                availability[acc] = fut.result()
            except Exception:
                availability[acc] = False

    return {"availability": availability}


def handle_fetch_structure(params: dict) -> dict:
    """Fetch and cache AlphaFold Cα coordinates for the given accession."""
    p = FetchStructureParams(**params)
    accession = p.accession.strip()
    if not accession:
        raise ValueError("accession is required")

    from kuma_core.kuro.alphafold import fetch_ca_coords

    coords = fetch_ca_coords(accession)

    if coords is None:
        with _core._state_lock:
            _core._state.ca_coords = None
            _core._state.ca_coords_accession = None
        return {"success": False, "error": f"AlphaFold structure unavailable for {accession}"}

    with _core._state_lock:
        _core._state.ca_coords = coords
        _core._state.ca_coords_accession = accession
    valid = sum(1 for c in coords if c is not None)
    return {
        "success": True,
        "accession": accession,
        "residues": valid,
    }


def _select_pdb_id(accession: str) -> str | None:
    """Pick a candidate PDB id from a UniProt accession's xref_pdb list.

    Returns the first cross-referenced PDB id (the caller verifies multi-chain
    eligibility via SIFTS). None when the entry has no PDB cross-reference.
    """
    try:
        req = urllib.request.Request(
            f"https://rest.uniprot.org/uniprotkb/{accession}.json?fields=xref_pdb",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, context=_get_ssl_ctx(), timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"UniProt xref_pdb fetch failed: {exc}") from exc

    for xref in data.get("uniProtKBCrossReferences", []):
        if xref.get("database") == "PDB":
            pdb_id = xref.get("id", "").strip()
            if pdb_id:
                return pdb_id
    return None


def _fetch_sifts_chains(pdb_id: str, accession: str) -> tuple[list[str], dict[int, int]]:
    """Return (chains, author->UniProt map) for *accession* in *pdb_id* via SIFTS.

    Uses the spike-verified offset-0 contract for 3N0G-class IspS structures:
    PDB author numbering equals UniProt numbering, so the author->UniProt map is
    identity across the SIFTS-covered ``[unp_start, unp_end]`` range. SIFTS label
    numbering (``residue_number``) is deliberately NOT used.
    """
    req = urllib.request.Request(
        f"https://www.ebi.ac.uk/pdbe/api/mappings/{pdb_id.lower()}",
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(req, context=_get_ssl_ctx(), timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    unp = data.get(pdb_id.lower(), {}).get("UniProt", {})
    seg = unp.get(accession)
    if not seg:
        return [], {}

    chains: list[str] = []
    author_to_unp: dict[int, int] = {}
    for m in seg.get("mappings", []):
        chain = m.get("chain_id")
        if chain and chain not in chains:
            chains.append(chain)
        unp_start = m.get("unp_start")
        unp_end = m.get("unp_end")
        # author == UniProt numbering (offset 0): identity over covered range.
        if isinstance(unp_start, int) and isinstance(unp_end, int):
            for pos in range(unp_start, unp_end + 1):
                author_to_unp[pos] = pos
    return sorted(chains), author_to_unp


def handle_fetch_interface_residues(params: dict) -> dict:
    """Compute dimer interface residues in the user ref_seq frame.

    Flow: accession -> xref_pdb (pick a PDB) -> SIFTS chains + author/UniProt
    map -> download coordinates -> crystal-contact interface (union of all
    chain pairs) -> map_residues into the ref_seq frame.

    Fail-fast: no PDB cross-reference returns an empty positions list with a
    descriptive note (AF-Multimer fallback is out of scope for v1); network
    failures surface in the ``error`` field rather than silently degrading.
    """
    p = FetchInterfaceParams(**params)
    accession = p.accession.strip()
    ref_seq = p.ref_seq.strip()
    if not accession:
        raise ValueError("accession is required")
    if not re.match(r"^[A-Za-z0-9_-]{1,20}$", accession):
        raise ValueError(f"Invalid UniProt accession format: {accession}")

    from kuma_core.kuro.interface import compute_interface_residues, map_residues

    # 1. accession -> candidate PDB id.
    try:
        pdb_id = _select_pdb_id(accession)
    except RuntimeError as exc:
        return {"interface_positions": [], "source": "error", "error": str(exc)}

    if not pdb_id:
        return {
            "interface_positions": [],
            "source": "none",
            "note": "no PDB; AF-Multimer fallback out of scope (v1)",
        }

    # 2. SIFTS chains + author->UniProt numbering map.
    try:
        chains, author_to_unp = _fetch_sifts_chains(pdb_id, accession)
    except Exception as exc:
        return {
            "interface_positions": [],
            "pdb_id": pdb_id,
            "source": "error",
            "error": f"SIFTS mappings fetch failed: {exc}",
        }

    if len(chains) < 2:
        return {
            "interface_positions": [],
            "pdb_id": pdb_id,
            "chains": chains,
            "source": "none",
            "note": "single-chain SIFTS mapping; no dimer interface to compute",
        }

    # 3. Download coordinates.
    try:
        dl_req = urllib.request.Request(
            f"https://files.rcsb.org/download/{pdb_id.upper()}.pdb"
        )
        with urllib.request.urlopen(dl_req, context=_get_ssl_ctx(), timeout=30) as resp:
            pdb_text = resp.read().decode("utf-8")
    except Exception as exc:
        return {
            "interface_positions": [],
            "pdb_id": pdb_id,
            "chains": chains,
            "source": "error",
            "error": f"PDB download failed: {exc}",
        }

    # 4. Union interface residues over all ordered chain pairs.
    author_residues: set[int] = set()
    for i, chain_a in enumerate(chains):
        for chain_b in chains:
            if chain_a == chain_b:
                continue
            author_residues |= compute_interface_residues(pdb_text, chain_a, chain_b)

    # 5. Map into the ref_seq frame (identity when ref_seq matches accession seq).
    if ref_seq:
        accession_seq = _fetch_accession_seq(accession)
        if not accession_seq:
            # Fail-fast: the ref_seq transform needs the accession sequence.
            # Do NOT silently return accession-frame positions mislabelled as
            # ref_seq-frame.
            return {
                "interface_positions": [],
                "pdb_id": pdb_id,
                "chains": chains,
                "source": "error",
                "error": f"accession FASTA fetch failed for {accession}; cannot map to ref_seq frame",
            }
        positions = map_residues(author_residues, author_to_unp, accession_seq, ref_seq)
    else:
        # No ref_seq supplied: report accession-frame positions directly.
        positions = {author_to_unp[r] for r in author_residues if r in author_to_unp}

    # 6. Oligomeric state (assembly API, reference only, never an interface filter).
    oligomeric_state = _fetch_oligomeric_state(pdb_id)

    return {
        "interface_positions": sorted(positions),
        "pdb_id": pdb_id,
        "chains": chains,
        "oligomeric_state": oligomeric_state,
        "source": "crystal_contact",
        "note": f"heavy-atom <5.0A chain-contact across {len(chains)} chains",
    }


def _fetch_accession_seq(accession: str) -> str:
    """UniProt canonical sequence for *accession* (empty string on failure)."""
    try:
        req = urllib.request.Request(
            f"https://rest.uniprot.org/uniprotkb/{accession}.fasta"
        )
        with urllib.request.urlopen(req, context=_get_ssl_ctx(), timeout=15) as resp:
            text = resp.read().decode("utf-8")
        return "".join(
            line.strip() for line in text.splitlines() if not line.startswith(">")
        )
    except Exception as exc:
        logger.warning("accession FASTA fetch failed for %s: %s", accession, exc)
        return ""


def _fetch_oligomeric_state(pdb_id: str) -> str | None:
    """Assembly-1 oligomeric state label (reference only, never a filter)."""
    try:
        req = urllib.request.Request(
            f"https://data.rcsb.org/rest/v1/core/assembly/{pdb_id.upper()}/1",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, context=_get_ssl_ctx(), timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("pdbx_struct_assembly", {}).get("oligomeric_details")
    except Exception as exc:
        logger.debug("oligomeric state fetch failed for %s: %s", pdb_id, exc)
        return None

def handle_fetch_pdb_text(params: dict) -> dict:
    """Fetch full PDB text for the given AlphaFold accession."""
    p = FetchPdbTextParams(**params)
    accession = p.accession.strip()
    if not accession:
        raise ValueError("accession is required")

    from kuma_core.kuro.alphafold import fetch_pdb_text

    pdb_text = fetch_pdb_text(accession)
    if pdb_text is None:
        return {
            "success": False,
            "accession": accession,
            "pdb_text": None,
            "source": "error",
        }
    return {
        "success": True,
        "accession": accession,
        "pdb_text": pdb_text,
        "source": "alphafold_cache",
    }


def handle_fetch_active_site(params: dict) -> dict:
    """Fetch UniProt Active site and Binding site positions for an accession."""
    p = FetchActiveSiteParams(**params)
    accession = p.accession.strip()
    if not accession:
        raise ValueError("accession is required")

    from kuma_core.kuro.uniprot_features import fetch_active_site_features

    return fetch_active_site_features(accession)


def handle_compute_dispersion(params: dict) -> dict:
    """Compute 3-D spatial dispersion for a set of positions."""
    p = ComputeDispersionParams(**params)
    if not p.accession.strip():
        raise ValueError("accession is required")
    if not p.ref_seq.strip():
        raise ValueError("ref_seq is required")

    from kuma_core.kuro.dispersion import compute_round_dispersion

    return compute_round_dispersion(
        accession=p.accession.strip(),
        ref_seq=p.ref_seq.strip(),
        positions=p.positions,
        n_trials=p.n_trials,
        seed=p.seed,
        pdb_text=p.pdb_text,
        coordinate_frame=p.coordinate_frame,
    )


def handle_predict_structure_esmfold(params: dict) -> dict:
    """Predict a reference-frame structure from sequence alone via ESMFold.

    No UniProt accession is required; the returned PDB is 1-based on the
    submitted sequence (coordinate_frame="reference"). Sequences over the public
    server's 400-residue limit are rejected before any network call. Failures
    surface as ``error_msg`` without leaking a traceback.
    """
    from kuma_core.kuro.esmfold import predict_structure

    p = PredictStructureEsmfoldParams(**params)
    sequence = p.sequence.strip()
    if not sequence:
        raise ValueError("sequence is required")

    try:
        pdb_text, plddt_mean, residue_count, cache_hit, seq_hash = predict_structure(
            sequence, progress=_progress,
        )
    except ValueError as exc:
        return {
            "success": False,
            "source": "error",
            "pdb_text": None,
            "plddt_mean": 0.0,
            "residue_count": 0,
            "coordinate_frame": "reference",
            "seq_hash": "",
            "cache_hit": False,
            "error_msg": str(exc),
        }

    return {
        "success": True,
        "source": "esmfold_cache" if cache_hit else "esmfold",
        "pdb_text": pdb_text,
        "plddt_mean": plddt_mean,
        "residue_count": residue_count,
        "coordinate_frame": "reference",
        "seq_hash": seq_hash,
        "cache_hit": cache_hit,
    }


def handle_annotate_domains_by_sequence(params: dict) -> dict:
    """Submit a protein sequence to InterProScan; return reference-frame DOMAIN annotations.

    Coordinates in ``ref_domains`` are 1-based on the submitted sequence
    (coordinate_frame="reference").  Results are cached by SHA-256 so repeated
    calls for the same sequence are served without a network round-trip.
    Network/protocol failures are surfaced as ``error_msg`` (no traceback leak).
    """
    from kuma_core.kuro.domains import _validate_sequence, _seq_sha256, run_interproscan

    p = AnnotateDomainsBySequenceParams(**params)
    sequence = p.sequence.strip()
    if not sequence:
        raise ValueError("sequence is required")

    email = _get_contact_email()

    try:
        seq_clean = _validate_sequence(sequence)
    except ValueError as exc:
        return {
            "domains": [],
            "protein_length": 0,
            "source": "error",
            "coordinate_frame": "reference",
            "ref_hash": "",
            "cache_hit": False,
            "error_msg": str(exc),
        }

    protein_length = len(seq_clean)
    # Allow caller-supplied ref_hash (e.g. already computed by frontend);
    # fall back to SHA-256 of the cleaned sequence.
    ref_hash = p.ref_hash or _seq_sha256(seq_clean)

    try:
        domains, cache_hit, computed_hash = run_interproscan(
            seq_clean,
            email,
            progress=_progress,
        )
    except ValueError as exc:
        return {
            "domains": [],
            "protein_length": protein_length,
            "source": "error",
            "coordinate_frame": "reference",
            "ref_hash": ref_hash,
            "cache_hit": False,
            "error_msg": str(exc),
        }

    if not domains:
        return {
            "domains": [],
            "protein_length": protein_length,
            "source": "interproscan",
            "coordinate_frame": "reference",
            "ref_hash": computed_hash,
            "cache_hit": cache_hit,
            "error_msg": "No DOMAIN-type InterPro annotations found for this sequence",
        }

    return {
        "domains": domains,
        "protein_length": protein_length,
        "source": "interproscan",
        "coordinate_frame": "reference",
        "ref_hash": computed_hash,
        "cache_hit": cache_hit,
    }
