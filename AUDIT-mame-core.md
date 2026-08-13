# MAME Core Defect Audit

Scope: every file returned by `rg --files kuma_core/mame | sort` on 2026-08-13. This was a findings-only pass: no source, test, or configuration file was modified. A concern appears under confirmed defects only when real `kuma_core.mame` code was executed with a concrete input and produced the stated bad result.

## 1. Coverage ledger

Filesystem inventory was captured before substantive source reading: **74 files**. All 74 were examined.

| File | Examined | Role and result |
|---|---:|---|
| `kuma_core/mame/__init__.py` | Yes | Package exports; stale FASTQ-gzip-only documentation noted, no result defect. |
| `kuma_core/mame/activity/__init__.py` | Yes | Activity public exports; no defect. |
| `kuma_core/mame/activity/aggregate.py` | Yes | Replicate mean/SD; finite cases correct; non-finite propagation belongs to C1 below. |
| `kuma_core/mame/activity/build_evolvepro_input.py` | Yes | Step 4 builder; C1 and C2 confirmed. |
| `kuma_core/mame/activity/constants.py` | Yes | WT label constants; intentional bare-WT rejection, no defect. |
| `kuma_core/mame/activity/evolvepro_xlsx.py` | Yes | Agilent/EVOLVEpro parser-writer; C1 non-finite ingress confirmed. |
| `kuma_core/mame/activity/export_evolvepro.py` | Yes | Activity export; propagates C1 non-finite values. |
| `kuma_core/mame/activity/ingest_long_csv.py` | Yes | Long CSV ingestion; accepts infinity, part of C1. |
| `kuma_core/mame/activity/join.py` | Yes | Activity/genotype join; lax well canonicalization contributes to C2. |
| `kuma_core/mame/activity/label_audit.py` | Yes | Closed-permutation label audit; no defect. |
| `kuma_core/mame/activity/merge.py` | Yes | Replicate priority merge; finite cases correct; C1 invariant absent. |
| `kuma_core/mame/activity/models.py` | Yes | Activity Pydantic models; allow non-finite values, part of C1. |
| `kuma_core/mame/activity/normalize.py` | Yes | Relative/log normalization; finite cases correct; C1 propagation. |
| `kuma_core/mame/activity/numeric_id_decode.py` | Yes | Numeric-report decoder; workbook-order replicate list is mean-only and result-neutral. |
| `kuma_core/mame/activity/plate_layout_xlsx.py` | Yes | Plate layout parser; C2 impossible-well acceptance confirmed. |
| `kuma_core/mame/activity/round.py` | Yes | Round persistence models; no defect. |
| `kuma_core/mame/activity/sanity_check.py` | Yes | Historical swap warning; no defect. |
| `kuma_core/mame/activity/variant_notation.py` | Yes | AA notation conversion; no defect. |
| `kuma_core/mame/activity/verdict_ngs.py` | Yes | Verdict workbook parser; contributes to C2. |
| `kuma_core/mame/barcode_worklist.py` | Yes | Barcode worklist generation; mutable contents in frozen carrier noted, no result failure. |
| `kuma_core/mame/cli.py` | Yes | Analyze/export CLI persistence; C3 round-trip data loss confirmed. |
| `kuma_core/mame/compare/__init__.py` | Yes | Compare exports; no defect. |
| `kuma_core/mame/compare/verdict.py` | Yes | Verdict classifier; manifests C13 false frameshift; legacy-indel concern remains H3. |
| `kuma_core/mame/detected.py` | Yes | Detection/recovery metrics; no defect. |
| `kuma_core/mame/distribution.py` | Yes | File-size distribution; non-finite producer not established, retained as H1. |
| `kuma_core/mame/export/__init__.py` | Yes | Export public API; no independent defect. |
| `kuma_core/mame/export/excel_writer.py` | Yes | Result workbook writer; C4 canonical-label collision confirmed. |
| `kuma_core/mame/export/janus_mapping.py` | Yes | JANUS mapping/export; C4 collision and C5 infinite volume confirmed. |
| `kuma_core/mame/export/nb_label.py` | Yes | Native-barcode canonicalization; root of C4 collision. |
| `kuma_core/mame/export/well_mapper.py` | Yes | Shared well-address compatibility seam; no defect. |
| `kuma_core/mame/health.py` | Yes | Run-health and cross-talk QC; C6 false-clean result confirmed. |
| `kuma_core/mame/ingest/__init__.py` | Yes | Ingest exports; no defect. |
| `kuma_core/mame/ingest/align.py` | Yes | Minimap2 adapter; C7 multi-record reference inconsistency confirmed. |
| `kuma_core/mame/ingest/amplicon_reference.py` | Yes | Amplicon resolution; C8 cross-contig fabrication confirmed. |
| `kuma_core/mame/ingest/barcode_package.py` | Yes | Primer/package builder; C9 flank violation, C10 circular length, C19 duplicate IDs confirmed. |
| `kuma_core/mame/ingest/barcode_tail.py` | Yes | Shared-tail inference; non-default C21 false tail confirmed. |
| `kuma_core/mame/ingest/combinatorial_demux.py` | Yes | Combinatorial demux/resume orchestration; no separate confirmed defect. |
| `kuma_core/mame/ingest/consensus.py` | Yes | Pileup and consensus metrics; scalar/vector and batch invariance exercised, no defect. |
| `kuma_core/mame/ingest/consensus_metadata.py` | Yes | FASTA metadata encoding; informational NaN accepted, included in H2. |
| `kuma_core/mame/ingest/demux.py` | Yes | Native demux; C11 stale output reuse confirmed. |
| `kuma_core/mame/ingest/fasta_parser.py` | Yes | Consensus FASTA reader; C12 NaN gate bypass and C18 manifest validation confirmed. |
| `kuma_core/mame/ingest/flow_cell.py` | Yes | Flow-cell report reader; C16 non-finite timestamp crash confirmed. |
| `kuma_core/mame/ingest/mode_router.py` | Yes | Ingest-mode routing; stray-unit propagation exercised, no defect. |
| `kuma_core/mame/ingest/polymerase.py` | Yes | Polymerase profiles; exact-name lookup matches callers, no defect. |
| `kuma_core/mame/ingest/quality_filter.py` | Yes | Read quality filtering; C14 NaN/Inf pass-through confirmed. |
| `kuma_core/mame/ingest/run_meta.py` | Yes | Run metadata discovery; C20 external symlink traversal confirmed. |
| `kuma_core/mame/ingest/run_pipeline.py` | Yes | Raw-run pipeline; manifest write/order and stats paths inspected, no separate defect. |
| `kuma_core/mame/ingest/sort_barcode.py` | Yes | Legacy native-barcode mapping; no defect. |
| `kuma_core/mame/ingest/stage_marker.py` | Yes | Resume marker validation; C17 malformed-shape crash confirmed. |
| `kuma_core/mame/ingest/unit_manifest.py` | Yes | Run-unit membership manifest; C18 schema/kind trust and C22 relative provenance confirmed. |
| `kuma_core/mame/ingest/well_consensus.py` | Yes | Per-well consensus orchestration; zero-read and propagation paths exercised, no defect. |
| `kuma_core/mame/io/__init__.py` | Yes | IO package marker; no defect. |
| `kuma_core/mame/io/kuma_meta.py` | Yes | Workbook metadata reader; workbook closure/absence behavior correct. |
| `kuma_core/mame/io/kuro_reader.py` | Yes | KURO expected-mutation reader; C15 malformed fields accepted as measurements. |
| `kuma_core/mame/io/plate_order_check.py` | Yes | Primer/expected order guard; C15 sparse/duplicate false agreement and C23 cap bug confirmed. |
| `kuma_core/mame/io/variant_list.py` | Yes | Variant-source routing; plain-list behavior correct; propagates C15 KURO defect. |
| `kuma_core/mame/layout.py` | Yes | Draft plate placement; C24 duplicate-mutant placement/capacity defect confirmed. |
| `kuma_core/mame/models.py` | Yes | Shared transfer models and thresholds; no independent defect. |
| `kuma_core/mame/perf.py` | Yes | Non-fatal instrumentation; broad catch is deliberate and does not affect results. |
| `kuma_core/mame/pipeline.py` | Yes | Analyze orchestration; selected-well scoping correct; no independent defect. |
| `kuma_core/mame/plate_geometry.py` | Yes | Canonical addressing and barcode layout checks; no defect. |
| `kuma_core/mame/qc/__init__.py` | Yes | QC exports; no defect. |
| `kuma_core/mame/qc/contamination.py` | Yes | Contamination signals; unavailable-vs-zero paths exercised, no defect. |
| `kuma_core/mame/qc/mapping_integrity.py` | Yes | Label-integrity QC; C25 false negative confirmed. |
| `kuma_core/mame/report/__init__.py` | Yes | Report public API; exposes C26 broken composition. |
| `kuma_core/mame/report/builder.py` | Yes | Report data builder; C26 drops renderer-required verdicts. |
| `kuma_core/mame/report/html_renderer.py` | Yes | HTML/SVG renderer; C26 all-empty plate map confirmed. |
| `kuma_core/mame/report/pdf_export.py` | Yes | Optional PDF/HTML fallback boundary; fallback exercised and correct. |
| `kuma_core/mame/run_quality.py` | Yes | Run quality and recurrence summary; absence handling and edge-position logic exercised. |
| `kuma_core/mame/select/__init__.py` | Yes | Selection exports; no defect. |
| `kuma_core/mame/select/best_pick.py` | Yes | Best-replicate selection; no confirmed defect; equal-fallback ordering remains H4. |
| `kuma_core/mame/select/purity.py` | Yes | Purity support/baseline; Wilson and empty-baseline cases correct. |
| `kuma_core/mame/translate/__init__.py` | Yes | Translation exports; no defect. |
| `kuma_core/mame/translate/aa_translator.py` | Yes | CDS translation/diff; C13 clamping defect confirmed. |

## 2. Confirmed defects

Severity follows the requested scientific ranking: **Category 1** wrong value reported as measured; **Category 2** silently dropped/double-counted data; **Category 3** unsupported input accepted; **Category 4** unknown reported as a number; **Category 5** reachable crash. Line numbers describe this audit revision.

### C1 — Category 1: non-finite or negative assay values produce a successful EVOLVEpro workbook

- **Location:** `activity/evolvepro_xlsx.py:93-105`, `activity/build_evolvepro_input.py:182-204`, with propagation through `normalize.py`, `aggregate.py`, `merge.py`, and `export_evolvepro.py`.
- **Executed input:** a one-variant Agilent workbook with area `nan`, `WT_1=10.0`, a valid layout/verdict, passed to `build_evolvepro_input`.
- **Wrong output:** `result 1 0`; output rows `[['Variant', 'activity'], ['1A', '']]`. A second run with `WT_1=-1, A1=-2` exported activity `2.0`.
- **Correct output:** reject non-finite or non-positive raw areas/WT denominators with a contextual error and publish no workbook.

### C2 — Category 1: impossible 96-well coordinates are accepted through Step 4

- **Location:** `activity/plate_layout_xlsx.py:20-21,59-65,187-209`, `activity/verdict_ngs.py:100-104`, `activity/join.py:20-35`.
- **Executed input:** layout `F1A,A0`, activity `WT_1=1; A0=2`, verdict `A0,F1A,PASS`.
- **Wrong output:** successful result with `[['Variant', 'activity'], ['1A', 2.0]]`; `A0` was normalized to `A00`. `A13` is accepted too.
- **Correct output:** reject anything outside `A01..H12` before mapping or NGS gating.

### C3 — Category 2: CLI JSON round-trip discards replicate plate/verdict data

- **Location:** `cli.py:146-249`.
- **Executed input:** one PASS verdict and a replicate whose `plate_verdicts={'NB01': verdict}`, round-tripped through `_dump_verdicts` and `_load_verdicts`, then exported.
- **Wrong output:** JSON retained `plate_keys=['NB01']`, but loaded `plate_verdicts=[]`; original Excel final row `['A1','NB01','1_1','mutant-1','PASS',...]` became `['A1',None,None,None,None,...]`. The same probe also showed current verdict metrics and fallback fields silently reset to defaults.
- **Correct output:** reconstruct each plate key from the already-built `by_key` mapping and round-trip every field required by export.

### C4 — Category 1/2: canonical NB-label collisions merge distinct physical plates

- **Location:** `export/nb_label.py:17-24`, `export/excel_writer.py:141-151,538-561`, `export/janus_mapping.py:409-432,577-581,680-696`.
- **Executed input:** two accepted native identifiers, `barcode01` and `NB01`, with valid PASS picks.
- **Wrong output:** Excel emitted duplicate `NB01_detected/read/quality` triplets and openpyxl renamed the second sheet `NB011`; JANUS assigned both physical sources to `Stock plate1` and the resolved deck contained only `{'NB01':'Stock plate1'}`.
- **Correct output:** reject ambiguous canonical labels or preserve collision-free identities; two physical plates must never share one rack.

### C5 — Category 1: infinite JANUS volume is written as an instrument instruction

- **Location:** `export/janus_mapping.py:539-542,683-696`.
- **Executed input:** `JanusSettings(volume=float('inf'))` with a valid PASS replicate.
- **Wrong output:** settings accepted it and device CSV contained literal `inf` in the volume cell.
- **Correct output:** reject every non-finite volume; only finite `volume > 0` is valid.

### C6 — Category 1: cross-talk QC reports extreme 5–8 barcode outliers as clean

- **Location:** `health.py:413-472`.
- **Executed input:** `{'barcode01':1_000_000, 'barcode02':100, ..., 'barcode05':100}`; repeated for populations through eight.
- **Wrong output:** `candidate_count=0, status='ok', outlier_z=1.7889`; no population below nine can reach the fixed 2.5 self-including z threshold.
- **Correct output:** report insufficient data below the mathematically reachable population, or use a leave-one-out/robust statistic if five-barcode detection is intended.

### C7 — Category 1/3: multi-record FASTA yields the wrong alignment reference length

- **Location:** `ingest/align.py:566,978,1043-1058`.
- **Executed input:** FASTA contig 1 = 300 bp, contig 2 = 1000 bp, with a read exactly matching contig 2.
- **Wrong output:** one alignment with stored `reference_length=300` and hit span 1000; strict full-span mode dropped the valid read entirely.
- **Correct output:** reject multi-record input under the documented one-record contract, or track the matched contig's 1000-bp length.

### C8 — Category 1/3: amplicon resolver fabricates a sequence across contig boundaries

- **Location:** `ingest/amplicon_reference.py:60-68,160-224`.
- **Executed input:** forward primer tail present only on FASTA contig 1 and reverse-complement tail only on contig 2.
- **Wrong output:** `extracted=True`, span `start=4,end=47`, with a sequence made by concatenating the two records.
- **Correct output:** reject the multi-record reference; no physical amplicon bridges two contigs.

### C9 — Category 1: flanking-primer windows violate the requested exclusion distance

- **Location:** `ingest/barcode_package.py:466-472,486-490,510-523,548-565`.
- **Executed input:** real 18-bp primer design with `flank_min=100`.
- **Wrong output:** forward binding `390:408` where end must be ≤400, reverse binding `682:700` where start must be ≥700, and `warnings=[]`.
- **Correct output:** account for primer length when enforcing both flanks; neither binding interval may enter the 100-bp exclusion zone.

### C10 — Category 1: circular package generation returns a negative amplicon length

- **Location:** `ingest/barcode_package.py:778-816`.
- **Executed input:** `generate_mame_package(..., topology='circular')` with forward position 1160 and reverse binding position 431.
- **Wrong output:** `amplicon_length=-710`, which is propagated as the later read-length target.
- **Correct output:** circular distance 490 bp for the exercised sequence, never a negative length.

### C11 — Category 2: rerunning native demux retains stale well FASTAs

- **Location:** `ingest/demux.py:476-546` (analogous output handling at 672+).
- **Executed input:** run 1 wrote one read to `well_A`; run 2 reused the directory and assigned its only read to `well_C`.
- **Wrong output:** returned counts `{'well_C':1}`, but disk contained both `well_A.fasta` and `well_C.fasta`; the next reader consumes stale `well_A`.
- **Correct output:** replacement semantics or an explicit refusal; output must contain only the current run's wells.

### C12 — Category 1: NaN consensus N-fraction bypasses the NO_CALL gate

- **Location:** `ingest/fasta_parser.py:226,393-411`.
- **Executed input:** FASTA header `depth=100 low_depth_positions=0 consensus_n_fraction=nan consensus_n_fraction_basis=covered` with sequence `NNN`.
- **Wrong output:** parsed fraction `nan`, evaluable `True`, verdict `PASS`. Control fraction `1.000` produced `NO_CALL`.
- **Correct output:** recover 3/3 N = 1.0 or reject non-finite metadata; never PASS.

### C13 — Category 1: CDS-end clamping creates a false FRAMESHIFT

- **Location:** `translate/aa_translator.py:195-225`, downstream `compare/verdict.py`.
- **Executed input:** reference `ATGAAATTTCCC` (12 bp), consensus reference + `AAA`, annotation `cds_start=0, cds_end=15`.
- **Wrong output:** `['13_INDEL','14_INDEL','15_INDEL']`, then verdict `FRAMESHIFT`.
- **Correct output:** query and reference both stop at computed comparable end 12; no NT changes and clean empty-design verdict `PASS`.

### C14 — Category 1: NaN/Inf sequencing-summary scores pass read filtering

- **Location:** `ingest/quality_filter.py:276-292,430-452`.
- **Executed input:** one 1000-bp Q2 FASTQ read with summary qscore `nan`.
- **Wrong output:** `n_input=1,n_passed=1,n_failed_qscore=0` and a FASTA record. Blank summary qscore correctly fell back to quality and failed; infinity also passes.
- **Correct output:** reject non-finite values or treat them as absent and use the quality-string fallback.

### C15 — Category 1/3: malformed KURO rows and sparse physical coordinates validate as correct

- **Location:** `io/kuro_reader.py:121-131,155-161`; `io/plate_order_check.py:86-124,187-196`.
- **Executed input A:** DESIGNED row `[V5F,'not-a-number',V,F,...]`.
- **Wrong output A:** `ExpectedMutation(position=0)`, label `V0F`; input validation returned `valid=True`. A blank mutant ID likewise produced an empty layout occupant while comparison used `V5F`.
- **Executed input B:** physical list `A1=V5F, C1=K53N` versus expected rows `V5F,K53N`; also a blank B grid cell and duplicated A1 coordinates.
- **Wrong output B:** `comparable=True,mismatched=False,ok=True`; sidecar validation returned `valid=True` although MAME maps the second expected row to B1.
- **Correct output:** refuse malformed required fields and any sparse/duplicate physical layout rather than compacting coordinates.

### C16 — Category 5: non-finite flow-cell timestamp aborts analysis

- **Location:** `ingest/flow_cell.py:121-131`.
- **Executed input:** otherwise valid `report_*.json` with `mux_scan_timestamp: NaN` (and separately infinity).
- **Wrong output:** `ValueError: cannot convert float NaN to integer`; infinity raised `OverflowError`.
- **Correct output:** advisory report parsing must skip/fallback for non-finite scans and never abort an otherwise completed analysis.

### C17 — Category 5: parseable malformed stage marker crashes resume

- **Location:** `ingest/stage_marker.py:368`.
- **Executed input:** valid `1_1.fasta` plus marker `{'wells':1}`.
- **Wrong output:** `TypeError: 'int' object is not iterable` from `is_unit_complete`.
- **Correct output:** `False` (invalid marker), followed by recomputation.

### C18 — Category 2/3: unsupported unit-manifest schema silently excludes plates

- **Location:** `ingest/unit_manifest.py:141-170`; duplicate trust path in `ingest/fasta_parser.py:562-567`.
- **Executed input:** directory containing `sort_barcode07` and `sort_barcode15`, manifest `{'schema_version':999,'kind':'foreign','units':['sort_barcode07']}`.
- **Wrong output:** only barcode07 loaded and barcode15 reported stray.
- **Correct output:** unsupported schema/kind makes no trusted membership claim, so both units load.

### C19 — Category 3: duplicate barcode identifiers silently overwrite seed sequences

- **Location:** `ingest/barcode_package.py:245-275`.
- **Executed input:** valid `fwd_1..12/rev_1..8` workbook plus a later different `fwd_1`.
- **Wrong output:** success with overwritten `fwd_1=CCCAA`, total 20.
- **Correct output:** ambiguity error naming the duplicate identifier.

### C20 — Category 3: run metadata follows an external directory symlink

- **Location:** `ingest/run_meta.py:156-164`.
- **Executed input:** sibling `linked_run -> /tmp/.../actual_run` containing `final_summary_x.txt`.
- **Wrong output:** metadata from the external run, including `flow_cell_id='FC-REAL'` and the external raw path.
- **Correct output:** no metadata; the module contract says symlinks/out-of-subtree paths are skipped.

### C21 — Category 3: public zero minimum returns a false barcode tail

- **Location:** `ingest/barcode_tail.py:94-101`.
- **Executed input:** `common_tail(['AAAAA','CCCCC'], min_length=0, min_seed=5)`.
- **Wrong output:** `'AAAAA'` despite no shared suffix.
- **Correct output:** `None`/empty result. Current production callers use safe defaults, so impact is limited to the public override.

### C22 — Category 1: manifest provenance claims an unnormalized relative run path

- **Location:** `ingest/unit_manifest.py:116-123`.
- **Executed input:** `run_dir=Path('relative-run')`.
- **Wrong output:** serialized `{'run_dir':'relative-run'}` although the schema promises an absolute run path.
- **Correct output:** absolute normalized provenance, or a corrected/refused contract.

### C23 — Category 3: a reporting cap of zero hides a real plate-order mismatch

- **Location:** `io/plate_order_check.py:187-196`.
- **Executed input:** same-size reversed expected/plate order with public `max_examples=0`.
- **Wrong output:** `mismatched=False,examples=[]`.
- **Correct output:** `mismatched=True`; diagnostic truncation must not determine the boolean.

### C24 — Category 1/2: multi-row mutants occupy multiple physical wells

- **Location:** `layout.py:86-127`.
- **Executed input:** expected rows for mutant `M1-double` at two positions plus mutant `M2`.
- **Wrong output:** `{'A1':'M1-double','B1':'M1-double','C1':'M2','D1':'WT'}` instead of one well per designed mutant. With 96 rows representing 95 distinct mutants, layout was empty and `M95` was reported dropped.
- **Correct output:** `{'A1':'M1-double','B1':'M2','C1':'WT'}`; the 95-mutant plate plus WT fits exactly.

### C25 — Category 1: mapping-integrity QC misses cross-matches owned by zero-observation wells

- **Location:** `qc/mapping_integrity.py:121-133`.
- **Executed input:** 24 observed wells with labels `X1..X24`, plus 24 other owner wells whose expected labels are `X1..X24` and whose observations are empty.
- **Wrong output:** `cross_match=0,cross_rate=0.0,suspect=False`.
- **Correct output:** denominator remains 24 observed wells, but expected-label universe includes all wells: `cross_match=24,cross_rate=1.0,suspect=True`.

### C26 — Category 2: documented report builder→renderer path renders every well empty

- **Location:** `report/builder.py:73-163`, `report/html_renderer.py:120,512-514`.
- **Executed input:** one PASS verdict at `NB01/1_1`; `render_html(build_run_report_data([verdict], []))`.
- **Wrong output:** data had no `_raw_verdicts`; SVG had 96 gray empty circles and zero PASS circles.
- **Correct output:** A1 green PASS and 95 empty wells. The sidecar patches a private attribute manually, while the public composition and tests that inject it conceal the loss.

## 3. Hypotheses

| Hypothesis | What would confirm it |
|---|---|
| H1 — `distribution.py` accepts non-finite file-size values and may emit NaN statistics or crash. | Demonstrate a reachable producer of non-finite file sizes, then execute the full report path. Normal `stat().st_size` inputs are finite. |
| H2 — `consensus_metadata.parse_noisy_positions` should reject non-finite fractions consistently with gate-bearing metadata. | Establish a consumer that treats the informational noisy-position fraction as a measurement or decision input; current consumers only report it. |
| H3 — legacy multiple `*_INDEL` markers can imply a false frameshift even when net indel is divisible by three. | Reproduce through a supported legacy persistence/ingest path where `consensus_net_indel_bp is None`; normal pipeline records carry the net value. |
| H4 — equal-volume fallback selection lacks a specified deterministic NB tie-break. | Establish an ordering contract for exact fallback ties and execute inputs whose insertion order changes the selected plate. |
| H5 — duplicate positions inside one malformed well inflate recurrence counts. | Produce such duplicates through a supported parser rather than direct construction; engine-built noisy positions are unique. |
| H6 — blank interior KURO rows compact plate order independently of C15. | Establish a physical-coordinate authority for an entirely blank expected row; without one, correct placement is ambiguous. |

## 4. Judged fine

- Missing run-unit manifests correctly mean “no claim,” not zero units; all directory units remain readable. The defect is limited to trusting an explicitly incompatible manifest.
- Contamination signals preserve `unavailable` separately from measured zero, including fully occupied plates and missing matrices.
- Consensus scalar/vector implementations and batch sizes produced equivalent metrics in focused tests; strand-share `None` versus measured `0.0` stayed distinct through the current core path.
- FASTQ reachability sampling includes both `.fastq` and `.fastq.gz` files.
- Reverse-strand CIGAR coordinate calculations were consistent in direct clipped/deletion cases.
- Default `common_tail()` settings reject too-short tails and tails that leave fewer than five seed bases; C21 requires the unsafe public override.
- `numeric_id_decode` preserves replicate file order rather than suffix order, but every current scientific consumer uses the mean, which is order-independent.
- Sorting Step 4 output by activity was not classified: no contract requiring physical/source order was found.
- The report PDF exporter’s optional-dependency HTML fallback completed correctly; its broad catches serve the explicit status-return boundary.
- JANUS duplicate-destination detection and compact-layout recovery passed focused tests; the confirmed JANUS defects concern native-label collision and non-finite volume instead.
- Selected-well analysis remains anchored to original plate positions and excludes undeclared occupants from scoring; no re-seating regression was found.
- The full existing suite does not prove these adverse cases: focused lanes passed hundreds of tests while the executions above still failed. The final full-suite run outside the socket-restricted sandbox produced **2,521 passed, 19 skipped, 0 failed**. Consolidated reproduction output is recorded at `/tmp/mame-audit-reproductions.txt`; the full-suite transcript is `/tmp/mame-audit-pytest.txt`.
