"""Handlers: external network calls — UniProt, InterPro, ESM embeddings."""

import json
import logging
import re

import sidecar.core as _core
from sidecar.core import (
    _get_ssl_ctx,
    logger,
)
from sidecar.models import FetchDomainsParams, SearchUniprotParams, FetchEsmEmbeddingParams


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

    import urllib.request as _urllib_req

    for url, db_label in endpoints:
        try:
            req = _urllib_req.Request(
                url,
                headers={"Accept": "application/json"},
            )
            with _urllib_req.urlopen(req, context=_get_ssl_ctx(), timeout=10) as resp:
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
        except Exception:
            continue

    # Both endpoints failed or returned no domains
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


def handle_search_uniprot(params: dict) -> dict:
    """Search UniProt for matching proteins via BLAST + optional direct lookup.

    Primary: BLAST the translation against UniProt Swiss-Prot via EBI BLAST API.
    Secondary: direct fetch if known_accession is provided.
    """
    p = SearchUniprotParams(**params)
    gene_name = p.gene_name.strip()
    organism = p.organism.strip()
    translation = p.translation.strip()
    known_accession = p.known_accession.strip()

    if not translation and not known_accession:
        raise ValueError("translation or known_accession is required")
    if known_accession and not re.match(r"^[A-Za-z0-9_-]{1,20}$", known_accession):
        raise ValueError(f"Invalid UniProt accession format: {known_accession}")

    import urllib.request as _urllib_req
    import urllib.parse as _urllib_parse
    import time as _time

    candidates: list[dict] = []
    auto_selected: str | None = None
    last_error: str = ""

    def _fetch_json(url: str) -> tuple[dict | None, str]:
        try:
            req = _urllib_req.Request(url, headers={"Accept": "application/json"})
            with _urllib_req.urlopen(req, context=_get_ssl_ctx(), timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8")), ""
        except Exception as exc:
            logger.warning("UniProt fetch failed: %s — %s", url, exc)
            return None, f"{type(exc).__name__}: {exc}"

    def _fetch_text(url: str) -> tuple[str, str]:
        try:
            req = _urllib_req.Request(url)
            with _urllib_req.urlopen(req, context=_get_ssl_ctx(), timeout=30) as resp:
                return resp.read().decode("utf-8").strip(), ""
        except Exception as exc:
            return "", f"{type(exc).__name__}: {exc}"

    seen_accessions: set[str] = set()

    # 1) Direct fetch by known accession
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
            candidates.append({
                "accession": acc,
                "name": ", ".join(gene_names) if gene_names else known_accession,
                "organism": data.get("organism", {}).get("scientificName", ""),
                "length": seq_data.get("length", 0) if isinstance(seq_data, dict) else 0,
                "identity": identity,
            })
            seen_accessions.add(acc)
            if identity == 100.0:
                auto_selected = acc

    # 2) BLAST search using protein sequence via EBI NCBI BLAST API
    if translation and not auto_selected:
        try:
            blast_data = _urllib_parse.urlencode({
                # TODO(security): Replace with user-configured email — hardcoded
                # placeholder violates EBI Terms of Use. Read from app config or
                # prompt user on first BLAST run.
                "email": "kuro-app@example.com",
                "program": "blastp",
                "database": "uniprotkb_swissprot",
                "stype": "protein",
                "sequence": translation.rstrip("*"),
            }).encode()
            submit_req = _urllib_req.Request(
                "https://www.ebi.ac.uk/Tools/services/rest/ncbiblast/run",
                data=blast_data,
                method="POST",
            )
            with _urllib_req.urlopen(submit_req, context=_get_ssl_ctx(), timeout=30) as resp:
                job_id = resp.read().decode().strip()

            # Poll for completion (max ~60s)
            status_text = ""
            for _ in range(20):
                _time.sleep(3)
                status_text, _ = _fetch_text(
                    f"https://www.ebi.ac.uk/Tools/services/rest/ncbiblast/status/{job_id}"
                )
                if status_text == "FINISHED":
                    break
                if status_text in ("FAILURE", "ERROR", "NOT_FOUND"):
                    raise RuntimeError(f"BLAST job failed: {status_text}")

            if status_text == "FINISHED":
                result_data, err = _fetch_json(
                    f"https://www.ebi.ac.uk/Tools/services/rest/ncbiblast/result/{job_id}/json"
                )
                if err:
                    last_error = err
                if result_data:
                    for hit in result_data.get("hits", [])[:10]:
                        # hit_acc is like "SP:Q50L36" or just accession
                        raw_acc = hit.get("hit_acc", "")
                        acc = raw_acc.split(":")[-1] if ":" in raw_acc else raw_acc
                        if acc in seen_accessions:
                            continue
                        seen_accessions.add(acc)
                        hsps = hit.get("hit_hsps", [])
                        blast_identity = hsps[0].get("hsp_identity", 0.0) if hsps else 0.0
                        # Parse organism from hit description: "... OS=Genus species ..."
                        hit_def = hit.get("hit_def", "")
                        os_m = re.search(r'\bOS=([^=]+?)(?:\s+\w+=|$)', hit_def)
                        hit_organism = os_m.group(1).strip() if os_m else ""
                        # Parse gene name
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

    candidates.sort(key=lambda c: c["identity"], reverse=True)

    if candidates and candidates[0]["identity"] >= 95.0:
        auto_selected = candidates[0]["accession"]

    return {
        "candidates": candidates,
        "auto_selected": auto_selected,
        "error_detail": last_error or None,
    }


def handle_fetch_esm_embedding(params: dict) -> dict:
    """Compute or fetch ESM-2 per-residue embedding.

    Accepts accession and/or sequence. Local inference is preferred
    when torch + fair-esm are installed; remote API is fallback.
    """
    p = FetchEsmEmbeddingParams(**params)
    accession = p.accession.strip()
    sequence = p.sequence.strip()
    if not accession and not sequence:
        raise ValueError("accession or sequence is required")

    from kuro.esm_embeddings import get_embedding

    embedding = get_embedding(accession=accession, sequence=sequence)

    if embedding is None:
        _core._state.esm_embedding = None
        return {"success": False, "error": "ESM-2 unavailable (install: pip install fair-esm torch)"}

    _core._state.esm_embedding = embedding
    return {
        "success": True,
        "accession": accession,
        "length": len(embedding),
        "dimension": len(embedding[0]) if embedding else 0,
    }
