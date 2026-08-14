# RPC sidecar correctness audit

Scope: every tracked file under `python-core/` on branch `audit-error-cases`. Generated `__pycache__/*.pyc` files are runtime artifacts and are excluded; the tracked inert `.gitkeep` is included. The filesystem currently contains 42 Python files plus `AGENTS.md` and `.gitkeep` (44 tracked files total).

## 1. Coverage ledger

| File | Examined | Role and result |
|---|---:|---|
| `python-core/AGENTS.md` | Yes | Defines the sidecar-local boundary and verification rules; no correctness finding. |
| `python-core/build_sidecar.py` | Yes | Orchestrates PyInstaller/resource copies; hypotheses: onedir copies only its launcher, and a stale executable minimap2 is accepted without a version check. |
| `python-core/scripts/bench_demux_match.py` | Yes | Benchmarks synthetic demux matching; hypothesis: non-positive repeat counts emit a fabricated 0 reads/s measurement. |
| `python-core/scripts/frozen_kuro_smoke.py` | Yes | Exercises the frozen KURO binary and minimal fixture imports; no correctness finding. |
| `python-core/scripts/frozen_mame_smoke.py` | Yes | Exercises frozen MAME RPC, multiprocessing, and exact derived-tail demux counts; no correctness finding. |
| `python-core/scripts/generate_mame_sample_result.py` | Yes | Builds the frontend sample response through production serializers; generated temporary `source_path` values affect disposable fixture provenance, not a scientific result. |
| `python-core/scripts/regen_mame_sample_barcodes.py` | Yes | Regenerates and reads back bundled barcode workbooks; hypothesis: verification does not assert the complete expected row set. |
| `python-core/scripts/regen_neb_offsets.py` | Yes | Fits the offline NEB Tm correction; low-impact hypothesis: residual metadata is computed before coefficient rounding. |
| `python-core/scripts/smoke_sidecar_io.py` | Yes | Sequential NDJSON smoke client; malformed/unexpected-line handling is appropriate for its single-request use. |
| `python-core/scripts/vendor-minimap2.py` | Yes | Provisions the pinned Linux minimap2 asset; hypothesis: Linux ARM is mapped to an x86-64 download. |
| `python-core/sidecar_kuro/__init__.py` | Yes | Package marker only; no behavior or finding. |
| `python-core/sidecar_kuro/core.py` | Yes | Owns KURO process state, locks, writer, caches, and shared path validation; no standalone finding, though cached mappings amplify the explicit-empty export defect. |
| `python-core/sidecar_kuro/dispatcher.py` | Yes | Routes registered RPCs and maps boundary exceptions; registry/locking are coherent, while accepted NaN values remain a model/handler defect. |
| `python-core/sidecar_kuro/handlers/__init__.py` | Yes | Package marker only; no behavior or finding. |
| `python-core/sidecar_kuro/handlers/design.py` | Yes | Designs/retries/swaps primer candidates and serializes metrics; confirmed partial swaps retain stale sequence-dependent measurements. |
| `python-core/sidecar_kuro/handlers/export.py` | Yes | Serializes KURO plates/orders/workspaces; confirmed explicit empty mappings fall back to cached primers, and non-finite Janus volume remains an additional hypothesis. |
| `python-core/sidecar_kuro/handlers/external.py` | Yes | Fetches UniProt/PDB/SIFTS/interface data; confirmed general SIFTS residue ranges are incorrectly forced to an identity map. |
| `python-core/sidecar_kuro/handlers/misc.py` | Yes | Handles EVOLVEpro selection/benchmarks and frame guards; confirmed non-finite weights truncate selection and substring structure coordinates are unshifted. |
| `python-core/sidecar_kuro/handlers/sequence.py` | Yes | Loads sequences and previews mutation text; confirmed preview accepts biologically invalid position 0. |
| `python-core/sidecar_kuro/handlers/settings.py` | Yes | Loads/saves preference bundles with reset-on-corruption behavior; no direct scientific-number finding. |
| `python-core/sidecar_kuro/models.py` | Yes | Defines KURO RPC/workspace schemas; confirmed non-finite selection input and ignored extra keys, plus range-validation hypotheses. |
| `python-core/sidecar_main_kuro.py` | Yes | KURO frozen NDJSON entrypoint; ready-before-import is diagnostic and does not gate dispatch, so no finding. |
| `python-core/sidecar_main_mame.py` | Yes | MAME frozen NDJSON entrypoint; `freeze_support()` correctly precedes dispatcher import, so no finding. |
| `python-core/sidecar_mame/__init__.py` | Yes | Package marker only; no behavior or finding. |
| `python-core/sidecar_mame/core.py` | Yes | Owns analyze state/path wrappers/JSON writer; state writes are coherent, though some consumers read without snapshots (hypothesis). |
| `python-core/sidecar_mame/dispatcher.py` | Yes | Routes MAME RPCs and asynchronous calls; scientific defects arise before serialization, while scalar-envelope handling remains a non-scientific robustness hypothesis. |
| `python-core/sidecar_mame/handlers/__init__.py` | Yes | Package marker only; no behavior or finding. |
| `python-core/sidecar_mame/handlers/activity.py` | Yes | Ingests/merges/exports activity measurements; confirmed infinity propagation and non-finite mismatch-threshold suppression. |
| `python-core/sidecar_mame/handlers/analyze.py` | Yes | Validates, ingests, classifies, serializes, persists, and reports MAME runs; confirmed flow-cell path, CDS interval, snapshot loss, non-finite threshold, empty-layout, and multi-record FASTA defects. |
| `python-core/sidecar_mame/handlers/barcode_package.py` | Yes | Builds barcode packages and flanking primers; permissive truncation/boolean/reversed-bound handling remains a hypothesis. |
| `python-core/sidecar_mame/handlers/barcode_worklist.py` | Yes | Applies declared layout selection and writes barcode worklists; invalid-label-to-empty behavior remains hypothesis 17 for this distinct output path. |
| `python-core/sidecar_mame/handlers/build_well_layout.py` | Yes | Builds and serializes draft layouts in core order; no direct finding beyond model extra-key acceptance. |
| `python-core/sidecar_mame/handlers/classify_round.py` | Yes | Reads round workbooks and produces transition advisories; confirmed the same workbook tripled becomes a confidence-1.0 stop decision. |
| `python-core/sidecar_mame/handlers/combinatorial_demux.py` | Yes | Orchestrates raw-run combinatorial demux and counters; whitespace/duplicate native-barcode handling remains a hypothesis. |
| `python-core/sidecar_mame/handlers/demux.py` | Yes | Runs legacy demux, quality filtering, consensus, and resume; confirmed FASTQ-only runs bypass the configured quality filter. |
| `python-core/sidecar_mame/handlers/detect_native_barcodes.py` | Yes | Reports byte-share barcode use; display rounding versus exact threshold is judged normal rounding, not a wrong measurement. |
| `python-core/sidecar_mame/handlers/export.py` | Yes | Re-exports cached results and Janus mappings; confirmed re-export erases designed-mutant provenance; suffix/format and strict-coercion concerns were not promoted without an executed wrong result. |
| `python-core/sidecar_mame/handlers/health.py` | Yes | Builds a locked run-health snapshot and preserves unavailable versus zero values; no finding. |
| `python-core/sidecar_mame/handlers/ingest.py` | Yes | Parses reference formats and serializes gene coordinates; routing/coordinates are coherent, no confirmed finding. |
| `python-core/sidecar_mame/handlers/kuma_meta.py` | Yes | Reads embedded workbook metadata; incomplete/wrong-role path acceptance is a boundary hypothesis, not a confirmed number defect. |
| `python-core/sidecar_mame/handlers/load.py` | Yes | Rehydrates analyze results; confirmed textual false values become true and scientific fields are lost through adjacent inverse serializers. |
| `python-core/sidecar_mame/handlers/report.py` | Yes | Builds reports from cached state; format/suffix mismatch and unlocked mixed-run snapshot remain hypotheses. |
| `python-core/sidecar_mame/models.py` | Yes | Defines major MAME request schemas; confirmed typo/default and bool-to-number coercion can silently change scientific parameters. |
| `python-core/vendor/minimap2/.gitkeep` | Yes | Inert placeholder for CI-populated binaries; no executable behavior or finding. |

## 2. Confirmed findings

The ranking numbers below use the request's seriousness order: rank 1 is a confidently reported wrong value; rank 2 is silent loss/double counting; rank 3 is accepted input the implementation cannot correctly handle; rank 4 is missing evidence represented as a measurement. Every item below was executed against the worktree with `PYTHONPATH=$PWD/python-core:$PWD /mnt/d/_workspace/cc/kuma/.venv/bin/python`. No production file was changed.

### F1 — Rank 1: a partial primer swap combines the new sequence with the old sequence-dependent measurements

- **Code:** `python-core/sidecar_kuro/handlers/design.py:50-53,509-546`.
- **Input executed:** Seeded the real KURO state with current forward primer `AAAA` (hairpin 1, homodimer 2, synthesis score 90, penalty 3) and candidate `GGGG` (99, 88, 10, 77), then called `handle_swap_primer({mutation: "A1V", candidate_idx: 1, swap_type: "fwd"})`.
- **Wrong output:** `forward_seq='GGGG'` and `tm_no_fwd=70.0`, but `hairpin_tm_fwd=1.0`, `homodimer_tm_fwd=2.0`, `synthesis_score_fwd=90.0`, and `penalty=3.0`. The hybrid is also installed in cached state and therefore reaches export.
- **Correct output:** The swapped sequence must carry its candidate's hairpin/homodimer/synthesis evidence and a penalty consistent with the resulting pair, or the RPC must recompute/refuse the partial hybrid.

### F2 — Rank 1: general SIFTS residue mappings are forced to the special-case identity map

- **Code:** `python-core/sidecar_kuro/handlers/external.py:534-566`.
- **Input executed:** Mocked a SIFTS mapping for chain A with UniProt 101..103 and PDB residues 5..7, then called `_fetch_sifts_chains("1ABC", "P123")`.
- **Wrong output:** `{101: 101, 102: 102, 103: 103}`.
- **Correct output:** `{5: 101, 6: 102, 7: 103}`. The current response drops or misplaces interface residues for ordinary PDBs whose author numbering is not the 3N0G identity special case.

### F3 — Rank 1: a substring-matching structure is accepted without shifting its coordinates into the reference frame

- **Code:** `python-core/sidecar_kuro/handlers/misc.py:160-189`.
- **Input executed:** Supplied structure sequence `XXABC`, reference `ABC`, and 1-indexed coordinates whose structure positions 1..5 are distinguishable.
- **Wrong output:** `mismatch=False`, the original coordinate list was returned unchanged, and reference position 1 read structure coordinate 1.
- **Correct output:** Reference position 1 must use structure position 3, or the handler must reject/fall back to 1-D. As returned, every downstream 3-D EVOLVEpro/benchmark distance is shifted by two residues.

### F4 — Rank 1: infinite activity values become infinite fold-change and log2 measurements

- **Code:** `python-core/sidecar_mame/handlers/activity.py:136-180` (the called reader only excludes NaN/negative values).
- **Input executed:** Uploaded a real long CSV containing WT `1` and mutant `inf`, then ran `handle_activity_merge` on a seeded round.
- **Wrong output:** The upload response contained `inf`; the merged mutant row reported both `fold_change=inf` and `log2_fc=inf`.
- **Correct output:** A row-specific finite-number validation error. Infinity is not an observed assay value and cannot be emitted as a scientific measurement (or strict JSON number).

### F5 — Rank 1: an invalid CDS interval validates successfully and converts real wells into false WRONG_AA verdicts

- **Code:** `python-core/sidecar_mame/handlers/analyze.py:1076-1087,1220-1224,1674-1683`.
- **Input executed:** Two real consensus records with expected `G2A`, `cds_start=9`, and `cds_end=3`.
- **Wrong output:** `handle_validate_inputs` returned `valid=True, errors=[]`; analyze translated both wells to an empty amino-acid sequence and returned `WRONG_AA` twice.
- **Correct output:** Both validation and analyze must refuse the request because start is not less than end (and bounds must be checked) before any verdict is calculated.

### F6 — Rank 1: an infinite replicate-mismatch threshold hides a measured disagreement

- **Code:** `python-core/sidecar_mame/handlers/activity.py:321-377`; the parallel model at `python-core/sidecar_mame/models.py:376` also has no finite/upper bound.
- **Input executed:** Authoritative mean 1.0, fallback mean 2.0 for `F89W`; compared `mismatch_threshold=0.1` with `mismatch_threshold=inf` through the real RPC handler.
- **Wrong output:** The finite request reported `mismatched=['F89W']`; the infinite request reported `mismatched=[]` and a plausible merged value of 1.0.
- **Correct output:** Reject non-finite thresholds. A one-unit disagreement cannot silently disappear because JSON admitted infinity.

### F7 — Rank 1: persisted textual false values restore as true scientific/state flags

- **Code:** `python-core/sidecar_mame/handlers/analyze.py:261-263,302-317`, reached by `handlers/load.py:90-113`.
- **Input executed:** Replayed `consensus_n_fraction_evaluable="false"`, `failed="false"`, and `is_fallback="false"`.
- **Wrong output:** All three restored as `True`; the same verdict carried `consensus_n_fraction=0.7` and was now labelled evaluable.
- **Correct output:** Reject non-boolean JSON types or parse an explicitly supported legacy encoding. Python truthiness must not invert the stated values.

### F8 — Rank 1: a NaN consensus threshold disables the gate and is serialized as an invalid numeric result

- **Code:** `python-core/sidecar_mame/handlers/analyze.py:1684-1724`; JSON writer `kuma_core/shared/sidecar.py:65-90`.
- **Input executed:** Ran analyze with two real consensus records and `max_consensus_n_fraction="NaN"`.
- **Wrong output:** Both records returned `PASS`; `compare_params.max_consensus_n_fraction` was `nan`, and serializing the response emitted bare `NaN`, which JavaScript `JSON.parse` rejects. Comparisons against NaN are false, so the configured ambiguity gate was silently disabled.
- **Correct output:** Reject every non-finite threshold before classification and serialization. An invalid threshold must not turn failing/unevaluable evidence into passing verdicts.

### F9 — Rank 1/2: explicit empty KURO mappings silently export cached primers from an earlier state

- **Code:** `python-core/sidecar_kuro/handlers/export.py:237-269,384-421,844-861`.
- **Input executed:** Seeded one cached plate mapping, mocked only file I/O, and called `handle_export_excel` with `mappings=[]` and `dedup_info={}`.
- **Wrong output:** Success response with `exported_mapping_count=1`; the explicit empty list took the truthiness fallback to cached state. `export_mapping` and `export_all` use the same branch, while their dry-run paths correctly distinguish `None` from `[]`.
- **Correct output:** Export zero mappings or refuse the empty request. It must never substitute primers from a prior design.

### F10 — Rank 2: the same round workbook can be counted three times and manufacture a confidence-1.0 stop advisory

- **Code:** `python-core/sidecar_mame/handlers/classify_round.py:421-459,468-472,501-592`.
- **Input executed:** A single workbook with ten sub-baseline activities. Once as round 1 it returned `continue_walking / calibration_period`. The identical path was then supplied as rounds 1, 2, and 3, with four WT values on the last entry.
- **Wrong output:** `label='stop'`, `reason='saturated_no_throughput'`, `confidence=1.0` although there was only one independent round measurement.
- **Correct output:** Reject duplicate paths/round identifiers (and non-increasing round sequences) or otherwise prove measurements are independent before accumulating them.

### F11 — Rank 2: FASTQ-only runs bypass the configured quality filter

- **Code:** `python-core/sidecar_mame/handlers/demux.py:670-681`.
- **Input executed:** One assigned Q0 FASTQ read, no sequencing summary, and `min_qscore=99.0` through `handle_demux_and_filter`.
- **Wrong output:** `n_assigned=1`, `filter_stats=None`, and the well FASTA existed. The adjacent comment says qualities are computed from FASTQ when no summary exists, but all filtering is inside `if sequencing_summary is not None`.
- **Correct output:** The read must fail the requested quality threshold, with filter statistics and no surviving well record, or the handler must refuse a mode in which it cannot apply the requested filter.

### F12 — Rank 2/4: analyze snapshot replay drops measured indel and purity evidence and substitutes defaults

- **Code:** serializer/deserializer in `python-core/sidecar_mame/handlers/analyze.py:140-204,226-298`; replay entrypoint `handlers/load.py:90-113`.
- **Input executed:** A `BarcodeRecord` carrying `n_indel_event_positions=4`, `max_indel_event_fraction=.375`, `min_variant_support=.82`, `n_variant_positions=2`, `min_variant_support_depth=37`, `max_del_run_length=3`, `consensus_net_indel_bp=-2`, and `median_read_net_indel_bp=1`, round-tripped through the production serializer pair.
- **Wrong output:** None of the eight keys was serialized; replay produced `0, 0.0, None, 0, 0, 0, None, None`. Later Excel export reads several of these fields, so a post-restart export is not the same scientific record.
- **Correct output:** Lossless round-trip of every downstream-consumed measurement, preserving unknown separately from measured zero.

### F13 — Rank 2: raw-run analysis searches the demux output for flow-cell history and loses measurements present in the run folder

- **Code:** raw input reassignment at `python-core/sidecar_mame/handlers/analyze.py:1656-1658`; later read at `:2084-2118`.
- **Input executed:** A raw MinKNOW fixture with `report_*.json` containing flow cell `FC-RAW` and pore scans 900 then 700; demux was stubbed only to keep the reproduction small.
- **Wrong output:** analyze returned `flow_cell_id=None, pore_start=None, pore_end=None`. Directly reading the original run folder returned `FC-RAW, 900, 700`.
- **Correct output:** Raw mode must use the original run directory for report/ledger identity, as it already does for run metadata.

### F14 — Rank 2/4: re-export erases the designed-mutant denominator from cached analyze state

- **Code:** `python-core/sidecar_mame/handlers/export.py:139-182`.
- **Input executed:** Cached an empty result with `last_designed_mutant_ids=frozenset({"F89W"})`, then called the real `handle_export_excel`.
- **Wrong output:** The workbook was written, but `get_state().last_designed_mutant_ids` became `None` because the state-refresh call did not forward it.
- **Correct output:** Re-export must preserve the original denominator/provenance. Otherwise a subsequent export reports recovery as unavailable rather than measured against one designed mutant.

### F15 — Rank 2: an empty effective layout drops every record and then reports zero off-layout records

- **Code:** selection parsing and counting in `python-core/sidecar_mame/handlers/analyze.py:597-619,648-661`; pipeline skip at `kuma_core/mame/pipeline.py:258-271`.
- **Input executed:** Analyzed two records at A1 and C1 with `selected_wells=["H12"]`, a valid but unused well. A separate validation call used `selected_wells=["Z99"]`.
- **Wrong output:** The H12 run returned zero verdicts and `off_layout_records={count: 0, wells: []}` despite skipping both records; provenance showed H12 unused. The separate validation call accepted Z99 with `valid=True` and no coordinate error.
- **Correct output:** Invalid coordinates must be rejected. If a valid selection yields an empty mapping, skipped records must still be reported (two here), not silently disappear behind the empty-dict truthiness guard.

### F16 — Rank 2/3: a non-finite KURO entropy weight silently returns fewer variants than requested

- **Code:** `python-core/sidecar_kuro/models.py:876-914` and `handlers/misc.py:194-230`.
- **Input executed:** `LoadEvolveproParams(entropy_weight=inf)` followed by production `pareto_diversity_select` on four candidates with `top_n=3`; finite control used 0.3.
- **Wrong output:** The model accepted infinity and selection returned only the seed candidate. The finite control returned three candidates.
- **Correct output:** Reject non-finite/out-of-blend-range weights. A requested three-variant selection cannot silently become one.

### F17 — Rank 3: request schemas silently discard typos and coerce booleans into numeric scientific parameters

- **Code:** representative MAME seams `python-core/sidecar_mame/models.py:23-112,455-484`; the models use permissive Pydantic defaults rather than strict/forbid configuration.
- **Input executed:** `coverage_fractoin=0.5`, `mapq_threshold=true`, `trim_flank_bp=false`, and `min_share=true` with otherwise valid existing paths.
- **Wrong output:** The typo disappeared and `coverage_fraction` reverted to 0.98; numeric fields became 1, 0, and 1.0. The response path proceeds as though these were deliberate settings.
- **Correct output:** Unknown keys and booleans for integer/float fields must be rejected at the RPC boundary.

### F18 — Rank 3: mutation preview accepts biological position zero as a valid mutation

- **Code:** `python-core/sidecar_kuro/handlers/sequence.py:49-75`.
- **Input executed:** `handle_parse_mutations_text({text: "A0V"})`.
- **Wrong output:** `parsed=[{raw: "A0V", wt_aa: "A", position: 0, mt_aa: "V"}], errors=[]`.
- **Correct output:** Reject the mutation at preview/parse time because the public mutation notation is 1-based and the later design path cannot use residue zero.

### F19 — Rank 3: multi-record FASTA references are concatenated into a biologically artificial sequence

- **Code:** `python-core/sidecar_mame/handlers/analyze.py:43-58`; the core pipeline independently repeats the behavior at `kuma_core/mame/pipeline.py:31-40`.
- **Input executed:** Supplied a two-record reference FASTA containing `>amplicon_A` / `ATG` and `>amplicon_B` / `TAA`, then ran the production reader and input validator.
- **Wrong output:** The reference became `ATGTAA`, and validation returned `valid=True, errors=[]` as though the cross-record junction were a real contiguous amplicon.
- **Correct output:** Refuse multiple FASTA records for this single-reference coordinate model (or require an explicit record choice); never synthesize a nonexistent contig junction.

## 3. Hypotheses

These were not promoted because the full wrong response was not independently executed in this pass.

1. **Demux resume identity omits result-determining parameters** — `python-core/sidecar_mame/handlers/demux.py:419-425,551-565`. Changing barcodes, error tolerance, quality/length filters, trimming, or linked-trim settings while reusing an output directory may reuse the old unit marker and old consensus. Confirm with two runs into one output, changing one parameter at a time, and assert recomputation plus changed contents.
2. **A zero-passing consensus well may survive in response/marker counts after its FASTA is deleted** — `demux.py:345-355,851-910`. Confirm with an assigned read that fails alignment/full-span and compare response counts, completion-marker inventory, and files on disk.
3. **Round bootstrap mixes raw-activity and log2 units** — `classify_round.py:70-84,470-473,553-589` and `kuma_core/strategy/classify.py:312-345`. The module itself records the mismatch. Confirm by running a calibrated fixture through current code and a units-consistent reference calculation and comparing confidence/decision boundaries.
4. **PyInstaller onedir packaging copies only the launcher** — `python-core/build_sidecar.py:197-221`. Confirm with an actual `--target kuro --onedir` build, then execute the copied Tauri-side launcher after removing/isolating the original dist tree.
5. **Bundled minimap2 is accepted without verifying the pinned version** — `python-core/build_sidecar.py:157-180`. Confirm by placing a harmless executable reporting another version in the expected vendor slot, building MAME, and inspecting/starting the bundle.
6. **Barcode sample regeneration can accept a missing indexed row** — `python-core/scripts/regen_mame_sample_barcodes.py:147-168`. Confirm by generating 19/20 expected rows (for example omit F12) and checking whether verification exits zero before replacing any shipped fixture.
7. **NEB residual metadata is calculated before coefficients are rounded for storage** — `python-core/scripts/regen_neb_offsets.py:74-92`. Confirm on a captured API matrix by recomputing residuals with the serialized four-decimal coefficients and comparing both reported residual fields.
8. **Report export can read a mixed-run state snapshot** — `python-core/sidecar_mame/core.py:87-101`, `handlers/report.py:52-87`. Confirm with a barrier-controlled concurrent state replacement during report construction; compare verdicts, replicates, metadata, and designed IDs in the emitted report.
9. **A non-positive benchmark repeat count can be reported as measured zero throughput** — `python-core/scripts/bench_demux_match.py:146-157`. Confirm in an environment with the benchmark dependencies by running `--repeat 0` and `--repeat -1`; the expected behavior is argument rejection rather than `0 reads/s` after no timed pass.
10. **Linux ARM provisioning selects the Linux x86-64 minimap2 asset** — `python-core/scripts/vendor-minimap2.py:154-164`. Confirm on Linux aarch64 (or a controlled platform probe) that the selected binary fails its executable/version check; the correct result is an explicit unsupported-platform response or a native ARM asset.
11. **KURO Janus transfer volume admits non-finite values** — `python-core/sidecar_kuro/models.py:595-612`, `handlers/export.py:785-827`. Confirm through the complete dispatcher/writer path with `transfer_vol="NaN"` and `"Infinity"`, then inspect both the JSON response and a non-empty generated worklist for invalid JSON/nonphysical instrument values.
12. **KURO boundary models admit invalid scientific ranges and boolean indices** — `python-core/sidecar_kuro/models.py:23-27,860-940`. Confirm each accepted negative/reversed domain or excluded range, non-positive dispersion position, free-form strategy, and boolean candidate index through its downstream handler and capture the resulting classification/selection rather than stopping at model acceptance.
13. **Barcode-package parameters may silently truncate, coerce booleans, or accept reversed bounds** — `python-core/sidecar_mame/handlers/barcode_package.py` and its request models. Confirm with a real package build using fractional integer fields, booleans, and reversed interval bounds, and compare the emitted sequences/coordinates with a strict reference or expected refusal.
14. **Combinatorial native-barcode input may preserve whitespace or duplicates as distinct assignments** — `python-core/sidecar_mame/handlers/combinatorial_demux.py`. Confirm with a minimal real demultiplexing fixture containing repeated and whitespace-padded barcode labels, then compare assigned-read and barcode counts with the normalized unique set.
15. **Embedded workbook metadata may accept an incomplete or wrong-role workbook** — `python-core/sidecar_mame/handlers/kuma_meta.py`. Confirm with production-generated workbooks whose metadata role or required keys are altered one at a time and observe whether the caller proceeds with defaulted scientific context instead of refusing the mismatch.
16. **Report/export filename suffixes and format selectors can disagree** — `python-core/sidecar_mame/handlers/export.py` and `handlers/report.py`. Confirm each supported format with a conflicting filename suffix, reopen the artifact according to both its declared response path and actual encoding, and capture any well-formed response that points to a misleading file type.
17. **Invalid selected wells may produce a successful zero-row barcode worklist** — `python-core/sidecar_mame/models.py:349-359`, `handlers/barcode_worklist.py:61-82`, and `kuma_core/mame/layout.py:135-155`. Confirm with a valid expected workbook and `selected_wells=["A13"]`; compare the returned row count/file contents with the expected coordinate-validation refusal.
18. **Valid JSON scalar envelopes may escape the MAME dispatcher error response** — `python-core/sidecar_mame/dispatcher.py:183-187,338-350`. Confirm by sending `[]`, `null`, and an object request with `params=[]` through the real NDJSON loop; the expected outputs are JSON-RPC `-32600`/`-32602`, not loop termination or an internal error.

## 4. Reviewed and judged correct

- MAME strand-share serialization deliberately omits `max_minor_allele_strand_share` and its counts when the share is `None`; it does not zero-fill unknown as the one-strand artifact measurement. `n_eligible_positions` remains unconditional because zero is a valid count.
- Analyze summary `fail_count = total - PASS - AMBIGUOUS` intentionally includes MIXED and every other non-detected class; `mixed_count` is a supplemental subset, not another disjoint bucket. The report builder uses the same semantics.
- Selected-layout off-layout counting does not normally double-count when the effective mapping is non-empty: skipped records produce no verdict, so verdict-derived and skipped-record counts are disjoint. The empty-effective-layout loss is confirmed as F15; KURO's distinct explicit-empty export fallback is confirmed as F9.
- Reference span response conversion is consistent: the internal span is zero-based half-open, `span_start` adds one, and `span_end` already equals the user-facing inclusive endpoint.
- MAME health takes a locked state snapshot and preserves unavailable versus zero values. Its absence states were reviewed specifically because this audit prioritizes fabricated zero measurements.
- Native-barcode `share` is rounded for display after the exact value drives `is_used`. A displayed 0.0500 beside false at a 0.05 threshold can occur at 0.04996; that is ordinary presentation rounding, not evidence the classifier used the rounded value.
- KURO dry-run mapping handlers use `is not None`, correctly distinguishing omitted mappings from an explicit empty list. They are the reference behavior that exposed F9 in the write handlers.
- The sequential frozen-smoke NDJSON client discards malformed/unexpected response lines, but it has only one in-flight request and still fails on EOF/timeout; this cannot attach another request's scientific result.
- The frozen MAME smoke has exact 12-well/24-read assertions for the derived-tail path. Its looser assertions cover packaging/liveness branches rather than claiming scientific golden values.
- `sidecar_main_mame.py` calls `freeze_support()` before importing the dispatcher, preventing frozen multiprocessing workers from re-entering the RPC loop.
