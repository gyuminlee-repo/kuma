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

- **reverse, closest Tm above the window**: the shortest legal reverse primer is already too hot. Common in GC-rich context. Two knobs reach this one, and an extreme GC window defeats both. **Tm tolerance** is capped at ±10 °C. The reverse **primer length** floor is editable in Parameters, the `R` field, default 19-27 bp. Automatic relaxation already tries both axes before the failure is reported, and it never takes the length floor under 18 nt, which is the bench rule this project holds itself to. A failure that survives both has run out of sequence rather than hit a setting.
- **reverse, closest Tm below the window**: the longest legal reverse primer is still too cold. AT-rich context. Raising tolerance also helps here.
- **forward**: usually a boundary problem, with too few bases downstream of the codon.
- **overlap**: no overlap length in the tried range lands in the overlap window.
- **full overlap**: the profile floors primer length above what the target Tm allows. Q5 SDM designs in full overlap mode by default.

Check the diagnostics for the forward, reverse and overlap stages to identify the failing constraint.

## Mutation count cap exceeded

Raised to 10,000 in v1.33.6. If you hit this, split the run.

## Reporting a problem

When none of the entries above settles it, **Diagnostics** in the menu bar
writes a diagnostics file to attach. It is more exact than retyping what the
screen said. The folder it lands in opens afterwards and nothing is sent
anywhere.

Its `run` section holds the request parameters of the most recent design
(polymerase, length ranges, Tm targets and `tol_max`, GC range, `overlap_mode`,
`strict_offtarget`, `auto_relax`), the success and failure counts, and the name
and reason of every failure. A reason sentence states which stage fell outside
which window, so that section alone decides most of the entries above. The file
also carries the app version and operating system, 50 progress messages and any
error-boundary record.

Sequences, template paths, project names and the mutations that succeeded stay
out. A mutation-notation parse failure quotes its own row and a wild-type
mismatch names the WT codon, so those two survive; the label and the reason are
both cut at a length limit, and a cut says so in the value.

`"status": "no-run-data"` means no design has run, or the inputs changed and the
previous outputs were discarded. `"request": null` means the result was restored
from a saved project, which does not store the design request. Running the
design again under the same settings before writing the file fills it in.
