# UniProt and AlphaFold

![UniProt candidates](../screenshots/07-uniprot-candidates.png)

Once a CDS is selected Kuro searches UniProt to enrich the design:

## BLAST-based match

The CDS translation is BLASTed against UniProt Swiss-Prot via EBI. The top hit is **auto-selected only if identity ≥ 95 %**; otherwise the candidate list is shown and you pick manually.

> **Contact email required.** EBI rejects BLAST jobs without an email. Configure `KURO_CONTACT_EMAIL` env or `contact_email` in `~/.kuro/config.json`. See [Configuration](configuration.md).

## Direct accession lookup

If your GenBank file has a `db_xref="UniProtKB/..."` qualifier, Kuro fetches the entry directly as the first candidate.

## Gene-name fallback

If BLAST fails, a UniProt gene-name search is tried — expect low-identity matches if the sequence is divergent.

## AlphaFold structure badge

Each candidate shows **AF** if a predicted structure exists. Selecting the candidate triggers Cα-coordinate download for 3D Pareto diversity — see [Diversity Strategies](diversity-strategies.md).

## ESMFold de-novo prediction (no accession)

When no UniProt accession is available — a novel or synthetic construct, or a low-identity BLAST result — the 3D panel can predict a structure directly from the reference sequence via **ESMFold** (EMBL-EBI ESMAtlas), after external-service consent. The prediction is in the reference frame (1-based on your sequence), so dispersion runs without accession mapping and pLDDT/variant/domain overlays stay valid. Active- and binding-site overlays require a UniProt accession and are hidden for ESMFold structures.

- **Limit**: the public ESMFold server accepts sequences up to 400 residues. Longer proteins (e.g. IspS) must use an AlphaFold accession.
- **Precedence**: uploaded PDB → AlphaFold-by-accession → ESMFold-by-sequence.
*Stub — candidate panel screenshot coming.*
