# Experimental Chainsaw interchange: input/output gate only

## Status / 현재 상태

This is an **offline, developer-facing export/inspection adapter**, not an enabled
application domain feature. It adds no GUI control, automatic prediction, network
request, package/model installation, ranking policy or selector input. A separate
experimental own-code wrapper can explicitly invoke an independently installed
external CPU environment; that environment and its licenses remain user-managed. The application does not call this module. Domain visualization and
candidate distribution UI remain unfinished; do not describe this as completed
Chainsaw integration. CLI output is a structural partition/coverage summary only.

현재 범위는 원본 전체 원자 보존과 입력·결과 대응을 검증하는 오프라인 연결부다.
앱에서 도메인 예측·표시가 활성화된 것은 아니다. FPS·기존 default·후보 CSV·가변
N·선정 가중치는 변경하지 않는다. 미할당 잔기는 linker/IDR/무기능 판정이 아니며
도메인 family/function 이름이나 interdomain 배치 신뢰도를 추정하지 않는다.

The prior public CPU pilot found that pinned Chainsaw can log a STRIDE failure,
exit successfully and return zero domains with high confidence for a CA-only
input. Consequently upstream exit status/confidence/TSV alone are insufficient.
Empty predictions are refused as inconclusive, even if a valid future run could
truly return no domains. This is a deliberately conservative v1 limitation.

## Input contract

`prepare_domain_input` takes original PDB text, its expected SHA-256, an explicit
`PolymerRecord` derived from independent complete-polymer evidence, and the
reference sequence. It never accepts the viewer's reference-indexed CA trace as
complete-backbone input. The CLI obtains this evidence through the existing local
ColabFold ZIP importer, including paired A3M, confidence, source hashes and exact
model/chain identity; it does not synthesize polymer evidence from ATOM rows.

Supported v1 inputs are intentionally narrower than the general importer:

- Standard 20-amino-acid protein with **identical full reference and polymer
  sequence**, all residue identities and N/CA/C/O observed. No tags, truncations,
  missing residues, homologs, missing backbone, modified residues or alternates.
- Explicit source PDB model and single-character chain. The pure API can select a
  particular model from a well-formed multi-model PDB; the ColabFold importer
  remains single-model. Duplicate/malformed model boundaries are refused.
- Source author residue integers/insertion codes are preserved in the manifest.
  Protein ATOM records must form the same ordered bijection as the independent
  complete polymer. Each normalized position maps to exactly one reference,
  polymer and source model/chain/author/insertion identity.
- Export normalizes residue labels to 1..N and chain A in `input.pdb`. All original
  selected protein ATOM lines are retained in order. Only chain/residue labels
  change; coordinate/occupancy/B-factor/element/charge/serial bytes remain exact.
  N/CA/C/O presence is a backbone gate, **not a claim of chemically complete side
  chains**. Waters/ligands outside the declared polymer and ancillary PDB records
  are omitted. Protein HETATM residues are refused. No atoms are fabricated.
- mmCIF/AF3 export is **not supported in this v1**. A lossless validated conversion
  and label/auth/model mapping are required before adding it.

The binding digest covers source and normalized structure hashes, reference hash,
polymer evidence source, frame, model, chain and every residue identity. It is
consistency metadata, not a digital signature. Read-only imports do not certify
that the input was genuinely produced by a named external service.

## Local developer workflow

From a source checkout with existing KUMA Python dependencies:

```sh
python scripts/domain_annotation_interchange.py export \
  --bundle local-colabfold.zip \
  --model demo_unrelaxed_rank_001_alphafold2_ptm_model_1_seed_000.pdb \
  --chain A --reference-file reference.txt --output-directory new-domain-job
```

Use the actual exact model member ID from bundle inspection. `reference.txt` is
plain uppercase complete protein sequence. The destination must not exist. This
writes `input.pdb` and `input.manifest.json`, and reports `prediction_executed:
false`. An existing destination is never overwritten. Output files are local;
this command does not transmit sequence/structure information.

The next step requires a separately installed, appropriately licensed official
Chainsaw/STRIDE environment. No installer or third-party runtime is supplied.
With Python 3.11 and the evaluated CPU torch 2.0.1+cpu environment, explicitly run:

```sh
/path/to/external/python scripts/run_external_chainsaw.py \
  --chainsaw-source /path/to/pinned/chainsaw --stride /path/to/stride \
  --input-directory new-domain-job --output new-result.json
```

The own-code wrapper verifies the pinned inference source/config/weights byte
hashes, enforces one CPU thread, uses a fresh temporary copy of `input.pdb` and
calls the official predictor with explicit chain A and `renumber_pdbs=True`.
It replaces only the in-memory STRIDE call boundary with its own subprocess
capture; it does not edit upstream files. Actual return code/stdout/stderr and all
ASG identities are retained before upstream deletes temporary files. The actual rewritten STRIDE input is
retained with its hash and all ATOM first-80 columns/order are checked against the
export before execution and again on import. Only cosmetic TER/END rewriting is
allowed, with no atoms after a terminator or extra model/heteroatom records. Missing or
partial ASG, nonzero exit, STRIDE stderr diagnostics, timeout (180 seconds), predictor
warnings, nonfinite values and empty/count-loss predictions prevent a successful
result file. It never manufactures success fields around a preexisting TSV.
Output paths must be fresh. The experimental CPU wrapper limits inputs to 2,000
residues; the pure interchange parser supports up to 9,999. Whole-model runtime
and memory are not a packaged application service contract; callers must bound
and cancel the external process. Product lifecycle/cancellation integration is
still unfinished.

Source/model hashes are consistency/provenance records, not a sandbox or proof
that a user's separately installed Python/dependencies/executable are trusted.
The user explicitly chooses the environment and executable. Windows and macOS
runtime compatibility are not established by Linux results.

When such an independently generated envelope exists, inspect it against the
**current original bundle and reference**, not only the old export:

```sh
python scripts/domain_annotation_interchange.py inspect \
  --bundle local-colabfold.zip \
  --model demo_unrelaxed_rank_001_alphafold2_ptm_model_1_seed_000.pdb \
  --chain A --reference-file reference.txt --result external-result.json
```

The command reparses/revalidates source evidence before decoding and writes only
an annotation JSON to stdout. Failure exits 2 without annotation stdout. No
workspace selection, CSV, app state or candidate score is written. Integrating
this into an asynchronous UI later must recheck `binding_sha256` immediately
before committing state as well as at decoding; this change has no async UI.

## External envelope v1

The decoder requires the exact input manifest plus these fields:

- `schema`: `kuma-chainsaw-result-v1`
- `tool_commit`: `9ced6e6d04043b0f2c50afa4527013997e305d4d`
- `weights_sha256`: `f21d5451e285e347582944e4017822379c31866d343593d71bccc8eb31ff9c9e`
  (upstream model_v3 weights measured in the public pilot)
- `input`: unchanged manifest generated by this adapter
- `renumber_pdbs`: boolean true
- `process`: `status: "ok"`, integer `exit_code: 0`, `warnings: []`
- `stride`: the same status fields, exact `residue_count`, and integer
  `assigned_positions: [1, ..., N]` from actual assignments, captured `stdout`,
  matching `stdout_sha256`, empty `stderr`, and the actual `stride_input_pdb`
  plus matching `stride_input_sha256`
- `prediction`: pinned upstream `chain_id: "input"` (file basename, **not chain
  selector**), matching `sequence_md5`, exact integer `nres`/`ndom`, nonempty
  `chopping`, finite `confidence` in 0..1 and nonnegative finite `time_sec`

The pinned source serializes chopping in the input's author residue labels.
Because the supplied input was explicitly normalized, only 1-based integer
segments are accepted here. `_` separates discontinuous segments of one domain;
`,` separates domains. Overlap, reversal, bounds errors and count mismatches are
refused. Results map back through the saved ordered identities, never by treating
original author integers as reference positions. The API insertion test includes
110A after renumbering and verifies exact identity recovery.

JSON is bounded to 8 MiB and captured STRIDE stdout to 4 MiB. ASG identities,
sequence, chain and finite assignment data are reparsed from that raw output.
Duplicate keys, nonfinite values, stale hashes/reference/model/
chain/weights/version and absent/error STRIDE evidence are refused. These checks
establish **internal consistency only**. A user can edit status/version/hash
claims, so they do not authenticate code execution, license rights or scientific
validity. Output retains `structural_partition_only_external_provenance_unverified`.
There are no function labels, linker labels, biological confidence thresholds or
selection weights.

## Licensing boundary

[Chainsaw's pinned MIT license](https://github.com/JudeWells/chainsaw/blob/9ced6e6d04043b0f2c50afa4527013997e305d4d/LICENSE)
does not replace the separate notices in its
[STRIDE materials](https://github.com/JudeWells/chainsaw/tree/9ced6e6d04043b0f2c50afa4527013997e305d4d/stride).
The inspected STRIDE/NSC notices contain academic/commercial/redistribution
restrictions. This change redistributes no Chainsaw/STRIDE code, binary, weights
or dependency and performs no hosted inference. Separately installed explicit
external execution is a conservative scope choice pending packaging/use review, **not a legal conclusion that invoking
any user-installed runner is forbidden**. That review and a robust runner can be
considered separately without weakening the input/output contract.

## Verification scope

Tests use public RCSB 1UBQ coordinates and synthetic mutations/envelopes. The CLI
subprocess test repackages public coordinates in a **synthetic ColabFold-like ZIP**;
it is not a genuine producer ZIP or native Chainsaw/STRIDE run. Tests cover exact
atom preservation, missing backbone/CA-only input, offset/insertion, model/chain
selection/ambiguity, stale context, malformed/empty/NaN/count-loss outputs, STRIDE
failure and discontinuous/unassigned membership. The binding test is a pure stale
result guard, not a native UI race simulation. Existing selection tests must also
run; no selection implementation depends on this adapter.

A fresh public Linux CPU external run and real STRIDE capture are recorded in
[the integration evidence](domain-annotation-pilot-20261010/README.md). This is
one integration fixture, not an accuracy benchmark. Mock-process failure tests
remain distinct from the real successful predictor run.

Unverified: real producer ZIP, user df_test, mmCIF/AF3 export, Windows/macOS
execution, native GUI, general protein chemistry, packaging rights, domain
accuracy/generalization, biological function and experimental utility.

## Public fixture provenance

`tests/data/domain_annotation/1ubq.pdb` is the public
[RCSB 1UBQ coordinate file](https://files.rcsb.org/download/1UBQ.pdb), retained from
the prior CPU pilot. Its exact SHA-256 is asserted in the test. Sequence evidence
is the original file's SEQRES record; synthetic changes and mock outputs are
explicitly test-only. Source publication: Vijay-Kumar, Bugg and Cook (1987),
Structure of ubiquitin refined at 1.8 Å resolution, J. Mol. Biol. 194:531–544,
[doi:10.1016/0022-2836(87)90679-6](https://doi.org/10.1016/0022-2836(87)90679-6).
