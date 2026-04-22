# Troubleshooting

## Sidecar process exited

The Python sidecar crashed during startup or an RPC call. Check `~/.kuro/crash.log` for the traceback.

Common causes:
- PyInstaller bundle missing a module (rare, reported as `ModuleNotFoundError`)
- Sequence file contains invalid characters
- Antivirus blocked the binary

## UniProt: no matching entries / low-similarity hits

BLAST needs an email. Set `KURO_CONTACT_EMAIL` or `contact_email` in `~/.kuro/config.json` — see [Configuration](configuration.md). With v1.33.6+ a default is used so BLAST works out of the box; low-similarity hits indicate BLAST itself failed (check internet, EBI status).

## "expected WT amino acid X at position N, but codon YYY encodes Z"

The mutation's WT letter doesn't match the CDS at that position.
- Wrong CDS selected? Switch gene in the dropdown — see [Gene Selection](gene-selection.md)
- 1-based vs 0-based? KURO positions are 1-based within CDS
- Isoform mismatch? Check the UniProt entry for your sequence

## Tm condition not met (many FAILs)

- Widen **Tm targets** ±2 °C
- Raise **Tm tolerance** (`tol_max`) in Advanced Options
- Enable **Fill on Failure** to pull buffer candidates

## CSV file missing required 'mutation' column

EVOLVEpro CSV must have a column named exactly `mutation` (case-sensitive). Rename your column.

## No valid primer pair found within Tm tolerance

All candidate windows failed. Check:
- Target residue near sequence boundary (not enough flanking bases)
- Extreme GC context (polyA/T stretches)
- Try a different polymerase with wider Tm range

## Mutation count cap exceeded

Raised to 10,000 in v1.33.6. If you hit this, split the run.
