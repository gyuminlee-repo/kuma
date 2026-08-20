# Troubleshooting

## Sidecar process exited

The Python sidecar crashed during startup or an RPC call. Check `~/.kuma/kuro/crash.log` for the traceback.

Common causes:
- PyInstaller bundle missing a module (rare, reported as `ModuleNotFoundError`)
- Sequence file contains invalid characters
- Antivirus blocked the binary

## UniProt: no matching entries / low-similarity hits

BLAST needs an email. Set `KURO_CONTACT_EMAIL` or `contact_email` in `~/.kuma/kuro/config.json` — see [Configuration](configuration.md). With v1.33.6+ a default is used so BLAST works out of the box; low-similarity hits indicate BLAST itself failed (check internet, EBI status).

## "expected WT amino acid X at position N, but codon YYY encodes Z"

The mutation's WT letter doesn't match the CDS at that position.
- Wrong CDS selected? Switch gene in the dropdown — see [Gene Selection](gene-selection.md)
- 1-based vs 0-based? Kuro positions are 1-based within CDS
- Isoform mismatch? Check the UniProt entry for your sequence

## Tm condition not met (many FAILs)

- Widen **Tm targets** ±2 °C
- Raise **Tm tolerance** (`tol_max`) in Advanced Options
- Enable **Fill on Failure** to pull buffer candidates

## CSV file missing required variant column

EVOLVEpro CSV must have one variant column named `variant`, `variants`, `mutation`, `mutations`, `mutant`, or `mutation_list` (first match wins, case-sensitive). Rename your column to one of these.

## No valid primer pair

Since v0.13.22 the reason names the stage that blocked the design, the closest Tm that stage could reach, the target window, and the length limits:

```
No valid primer pair - reverse: closest Tm 64.4C at 19 bp, outside 58+-4.0C (length 19-27 bp)
```

Read the stage first.

- **reverse, closest Tm above the window**: the shortest legal reverse primer is already too hot. Common in GC-rich context. Raise **Tm tolerance**, since the length floor cannot be lowered from the UI.
- **reverse, closest Tm below the window**: the longest legal reverse primer is still too cold. AT-rich context. Raising tolerance also helps here.
- **forward**: usually a boundary problem, with too few bases downstream of the codon.
- **overlap**: no overlap length in the tried range lands in the overlap window.
- **full overlap**: the profile floors primer length above what the target Tm allows. Q5 SDM designs in full overlap mode by default.

The stage that blocks is not always the one you expect. On a 95-mutation IspS run every failure came from the reverse primer, and no failure came from the forward primer or the overlap.

## Mutation count cap exceeded

Raised to 10,000 in v1.33.6. If you hit this, split the run.
