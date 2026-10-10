# Public Linux external-wrapper integration evidence

Date: 2026-10-10 UTC. One public protein fixture; no new structure prediction,
private data, GPU, hosted service, accuracy comparison or domain-based selection.
The actual external predictor was pinned official Chainsaw with a separately
compiled STRIDE in a task-owned research environment. No third-party source,
weights, executable or dependencies are included in this change.

## Recorded result

- Original [RCSB 1UBQ](https://files.rcsb.org/download/1UBQ.pdb), model 1 / chain A.
  Independent original SEQRES sequence: 76 residues. All 602 original selected
  protein ATOM records were exported with coordinate/occupancy/B-factor/atom
  fields unchanged; only chain/residue labels were normalized.
- Own wrapper process exited 0, stderr empty. Actual STRIDE subprocess exited 0;
  all 76 ASG identities/sequence positions were captured and checked before
  upstream removed temporary files. Captured stdout has its own SHA-256 and the
  executed STRIDE binary hash is retained in the result. The actual input PDB
  passed to STRIDE is also retained and verified against all 602 exported ATOM
  first-80-column records in order. Its raw hash differs solely because the
  pinned upstream renumberer pads/renumbers TER and pads END; coordinate changes,
  atom loss/reordering, extra model records and atoms after TER are refused.
- Chainsaw returned one domain, normalized/reference positions **2–71**, assigned
  **70/76 (92.1053%)**. Positions 1 and 72–76 remain unassigned. Confidence was
  0.9934999942779541, which is **not** a calibrated functional/fitness probability.
- `1ubq-external-result.json` is the actual final envelope, including raw STRIDE
  output, version/source/weight hashes, complete residue mapping and normalized
  input hash. `summary.json` records the checks and limits. The ordinary unit
  suite replays that saved result against original source atoms; replay is not a
  fresh inference run. Timing in the upstream row is not a benchmark claim.
- Real wrapper failure probes using controlled stand-ins for the STRIDE process:
  nonzero exit and successful exit with empty stdout both exited 2 and created no
  result file. These are **mock STRIDE process tests**, not independent scientific
  predictions. Unit tests additionally cover timeout, diagnostics, missing or
  mismatched ASG, CA-only/backbone loss, author/insertion, stale identity and NaN.

The earlier comparison benchmark genuinely ran native Linux inference but did
not preserve STRIDE ASG or its individual process exit status. Its deleted
intermediate evidence was not reconstructed or relabeled as satisfying the new
contract. This fresh run supplies the new evidence.

## Reproduce with an independently prepared environment

The wrapper does not install anything. Review Chainsaw and separate STRIDE/NSC
use/redistribution terms before preparing an external environment. The tested
research environment used Python 3.11.17, torch 2.0.1+cpu, numpy 1.24.3, scipy
1.10.1, biopython 1.81, einops 0.6.1, pydantic 1.10.8 and pandas 2.0.1. These are
historical compatibility pins, not a reviewed production security/maintenance
policy. Exact inference-source/config/model-v3 hashes are checked against
`scripts/chainsaw-source-pins.json`.

From the repository root, with KUMA's normal Python for the pure adapter, export
the preserved public source (the target `public-domain-job` must be new):

```sh
python - <<'PY'
from pathlib import Path
import hashlib, json
from kuma_core.kuro.domain_annotation import prepare_domain_input, _AA
from kuma_core.kuro.residue_mapping import PolymerRecord, ResidueId
source = Path('tests/data/domain_annotation/1ubq.pdb').read_text()
sequence = ''.join(_AA[aa] for line in source.splitlines()
                   if line.startswith('SEQRES') and line[11] == 'A'
                   for aa in line[19:70].split())
ids = tuple(ResidueId('1', 'A', int(line[22:26]), line[26].strip())
            for line in source.splitlines()
            if line.startswith('ATOM  ') and line[21] == 'A'
            and line[12:16].strip() == 'CA')
polymer = PolymerRecord(sequence, 'RCSB 1UBQ SEQRES; public full-polymer evidence',
                        'public-1ubq-original', '1', 'A', ids)
prepared = prepare_domain_input(source, polymer, sequence,
                                source_sha256=hashlib.sha256(source.encode()).hexdigest())
out = Path('public-domain-job'); out.mkdir()
(out / 'input.pdb').write_text(prepared.normalized_pdb, newline='\n')
(out / 'input.manifest.json').write_text(json.dumps(prepared.manifest(), indent=2))
PY
"$CHAINSAW_PYTHON" scripts/run_external_chainsaw.py \
  --chainsaw-source "$CHAINSAW_SOURCE" --stride "$STRIDE_EXECUTABLE" \
  --input-directory public-domain-job --output public-domain-result.json
```

Set those three environment variables to an existing installation you are
entitled to use. The run must be in a fresh Python process; caller supervision
should bound whole-process time (300 seconds was used for this 76-residue test).
No automatic install/download is triggered. For a genuine ColabFold output, use
the export/inspect CLI documented in the parent interchange contract instead;
this public PDB test is not a genuine producer ZIP.

Validate the saved envelope through `decode_domain_result` against a freshly
prepared original-source `DomainInput` and current binding. The permanent test
`test_recorded_native_public_result_replays_against_original_atoms` demonstrates
that integrity check without depending on the external runtime.

## Limits

This validates the **experimental command-line integration boundary on Linux**.
It does not enable app annotation UI, candidate distribution plots, selection
weights, FPS changes or a managed background service. Real producer ZIP, user
candidate data, mmCIF/AF3 export, Windows/macOS native execution, native Tauri GUI,
model packaging, domain accuracy/function and biological utility remain
unverified. The four-case earlier comparison is a separate pilot with its own
sampling/exposure limitations.
