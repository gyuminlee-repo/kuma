# Changelog

## v0.13.23 (Rescue levers that run, verdicts that stop overclaiming, annealing below extension)

A defect audit run straight after v0.13.22, aimed at one pattern: a declared contract that the code quietly contradicts, with nothing checking the two against each other. That is what the v0.13.22 Tm scale bug was, and five sweeps (constant provenance, hard bounds, hidden diagnostics, cross-layer drift, MAME thresholds) found more of it.

### Fixed
- v0.13.23: The Tm tolerance control now reaches the batch design. The frontend sent `tol_max` on every request, `DesignSdmPrimersParams` had no such field, and Pydantic dropped it silently under the default `extra="ignore"`, so the batch always ran at 4.0 while only the retry path honoured the value. Moving the control from 4 to 10 changed nothing. On a 95-mutation IspS input the yield now moves 91/95 at tolerance 4, 94/95 at 6, and 95/95 at 8. Auto-relax widens from the requested value rather than a constant, so asking for 8.0 no longer produces a 6.0 rescue narrower than the first attempt. (`python-core/sidecar_kuro/models.py`, `kuma_core/kuro/sdm_engine.py`, `python-core/sidecar_kuro/handlers/design.py`, `src/components/panels/ParameterPanel.tsx`)
- v0.13.23: Auto-relax rescue runs without a rescue pool. The block sat inside a guard that also required `rescue_pool`, and the frontend sends an empty pool outside EVOLVEpro mode, which made auto-relax dead code for manual and CSV input. Measured with an empty pool, the same input moves from 91/95 to 94/95. (`python-core/sidecar_kuro/handlers/design.py`)
- v0.13.23: A well counts as recovered only when its designed mutation is confirmed. The indel-event gate returned AMBIGUOUS before the expected mutation was ever compared, and `detected.py` treats AMBIGUOUS as a guarantee that every expected mutation matched, so a deletion-bearing well whose consensus lacked the designed mutation reported a recovery rate of 1.0 and won replicate selection. (`kuma_core/mame/compare/verdict.py`)
- v0.13.23: `consensus_n_fraction` is scoped to covered positions. Dividing by the whole alignment reference sent every well to NO_CALL when the reference was a plasmid map, which the translator explicitly supports: 150 perfect reads carrying the designed mutation measured 0.97. A file written before this change is recovered exactly from `low_depth_positions`, and when that is unavailable the value is marked unevaluable and the gate is skipped with a note, rather than reusing a differently defined number. (`kuma_core/mame/ingest/consensus.py`, `fasta_parser.py`, `consensus_metadata.py`)
- v0.13.23: A coordinate-origin mismatch fails loudly. The expected WT residue was parsed and discarded, so a tag, leader peptide, or plasmid offset shifted a whole plate onto the wrong residues and still reported PASS with empty notes. (`kuma_core/mame/compare/verdict.py`)
- v0.13.23: Cross-talk reports whether it ran. Four states, including a missing input file and a parse failure, collapsed into an empty list that the panel rendered as an all-clear, in a section that sat outside the MinKNOW guard. The z-score population also included the `unclassified` bin, which demux excludes by name, so a large unclassified count hid the real candidate. (`kuma_core/mame/health.py`, `src/components/mame/widgets/RunHealthPanel.tsx`)
- v0.13.23: Wells that cannot be identified stay unidentified. A failing well with no label match and no sample_map entry was attributed to `expected[idx % len(expected)]`, so its position in the ingest list decided which mutant it joined. (`kuma_core/mame/pipeline.py`)
- v0.13.23: The verdict inspector shows the note instead of an invented identity. The Identity row rendered 100 minus five per observed AA change; no identity field exists anywhere in the backend. (`src/components/mame/layout/MameInspectorContent.tsx`)
- v0.13.23: Recommended annealing never exceeds the extension temperature. Q5 SDM carried no two-step threshold, so all eleven pairs the fixture designs were recommended 74 to 79 C against a 72 C extension step. The demotion also tested the raw Tm rather than the annealing temperature NEB specifies, and Phusion lacked the documented sub-20-nucleotide branch. Across all eight profiles, pairs above 72 C fall from 12 to 0. (`kuma_core/kuro/annealing.py`, `kuma_core/kuro/resources/polymerase_profiles.json`)
- v0.13.23: The KURO sidecar surfaces the exception type and message instead of a bare "Internal error", matching the MAME sidecar under the same -32603 code. (`python-core/sidecar_kuro/dispatcher.py`)

### Known issues
- Reported MAME numbers can move. Scoping the N fraction to covered positions and requiring the designed mutation before AMBIGUOUS both change verdicts on existing data, and a coordinate-origin mismatch that used to pass now aborts the run. On an 8-well panel the distribution moves NO_CALL -5, PASS +3, WRONG_AA +2, with no well flipping into a false PASS.
- A well whose N fraction is unevaluable serializes as 0.000, so Excel, CLI, and the frontend read it as clean. The reason is carried in `verdict_notes` on the same row.
- The pool-cascade branch still designs at the default tolerance.

---
## v0.13.22 (SDM design Tm scale correction, failure reasons that name the blocking stage)

### Fixed
- v0.13.22.1: The design-time Tm no longer carries the Mg and dNTP terms the Benchling scale does not model. v0.13.19.0 pinned one fixed scale for every polymerase but populated it with a polymerase buffer (Mg 1.5 mM, dNTP 0.8 mM), while the Benchling SantaLucia 1998 calculator models monovalent salt and oligo concentration only. Every design Tm therefore ran about 5.4 C hot against unchanged 62/58/42 targets, and GC-rich sites lost their reverse primer: the shortest legal 19 bp reverse already exceeded 58+-4, so the site failed. Verified against a pair designed at the bench on pTSN-PtIspS-idi(KanR) F385Y, where Benchling reports 61.6 / 59.5 C and the corrected scale reproduces 61.2 / 59.5 C; the engine now regenerates that reverse primer byte for byte. Yield on a 95-mutation IspS input moves from 74/95 to 91/95 before rescue and 94/95 with auto-relax, and the 50-mutation dmpR fixture from 21/50 to 36/50. Targets, primer lengths, and the enzyme-specific annealing temperature path are untouched. (`kuma_core/kuro/sdm_engine.py`)
- v0.13.22.1: A failed mutation now reports which stage blocked it instead of one generic tolerance line. The reason names the overlap window, the forward primer, the reverse primer, or the full-overlap gate, and carries the closest reachable Tm, the target window, and the length limits, for example `reverse: closest Tm 64.4C at 19 bp, outside 58+-4.0C (length 19-27 bp)`. Diagnosis runs only after a failure is confirmed, so the success path is unchanged, and it observes through the same search primitives rather than reimplementing the ladder, so the message cannot drift from the search. (`kuma_core/kuro/sdm_engine.py`, `tests/test_sdm_engine.py`)

### Changed
- v0.13.22.0: KURO step 2 loads EVOLVEpro and Others through one loader with optional column mapping, `resetAll` no longer leaks candidates, export BOM is selected by locale, and UniProt BLAST auto-search is gated. (`src/store/slices/inputSlice.ts`, `src/store/slices/sequenceSlice.ts`, `src/store/slices/exportSlice.ts`)

### Known issues
- One IspS mutation (L265F) still fails, with the reverse primer at 64.4 C against 58+-6 even after auto-relax. The cause is the 19 bp reverse length floor, which is kept at the value the paper method specifies.

---
## v0.13.19 (Paper-standard SDM design for every polymerase)

### Changed
- v0.13.19.0: SDM design targets are now **method-level constants** (Fwd 62 / Rev 58 / Overlap 42 C, mutation site at least 4 bp from the 3' end) for **every** polymerase profile, and the design-time Tm runs on one fixed scale. Previously only the Benchling profile carried the paper values; the others derived targets from `opt_tm` (`opt_tm`, `-4`, `-20`), so selecting KOD or Q5 silently designed to 68/64/48, and the design Tm itself was computed on a per-enzyme scale (NEB-calibrated for Q5/Phusion/Taq). Every profile that shares the length spec now designs byte-identical primers matching the paper reference, and enzyme identity affects only the recommended annealing temperature. Targets and lengths follow Landwehr et al. 2025 (Nat Commun 16, 865), whose SI Fig. S4 defines 62/58 as whole-primer melting temperatures. (`kuma_core/kuro/sdm_engine.py`, `kuma_core/kuro/resources/polymerase_profiles.json`, `src/store/slices/designSlice.ts`)

### Fixed
- v0.13.19.0: CI now smoke-tests the frozen KURO sidecar (spawn, `ping`, `load_fasta`, import-stage marker) so an import crash cannot reach a release. The v0.13.17 startup failure shipped because the pipeline only checked that the binary existed. (`python-core/scripts/frozen_kuro_smoke.py`, `.github/workflows/build.yml`)

---
## v0.13.18 (Sidecar startup fix on non-UTF-8 Windows locales)

### Fixed
- v0.13.18.0: The KURO sidecar no longer dies at import on Windows systems whose locale encoding is not UTF-8 (cp949 on Korean Windows, for example). The profile loader opened the bundled polymerase table with the locale default encoding, so the non-ASCII touchdown text introduced in v0.13.17 raised `UnicodeDecodeError` before any RPC could run, which surfaced as "Sidecar process exited" for every command including sequence loading. The loader now pins utf-8, matching the three other readers in that module, and a regression test drives the registry under `PYTHONWARNDEFAULTENCODING` so a locale-default open cannot come back. (`kuma_core/kuro/polymerase.py`, `tests/test_polymerase.py`)

---
## v0.13.17 (Per-enzyme annealing temperature)

### Added
- v0.13.17.0: KURO now outputs a **recommended annealing temperature (Ta)** per SDM primer pair, calibrated to the selected polymerase with verified manufacturer rules: NEB Q5 (Tm+1), Phusion (Tm+3), Taq (Tm-5) via the existing NEB Tm offsets; KOD One (nearest-neighbor Tm-5, 3-step, step-down 74/72/70/68); Takara PrimeSTAR GXL (discrete 55/60); Thermo DreamTaq (Wallace, Tm-5), with 2-step promotion for high-Tm pairs. The design-time Tm scale (Fwd 62 / Rev 58 / Overlap 42) stays unchanged; Ta is an additive output in the result table with a mode and touchdown tooltip. Rules verified against primary sources (NEB Tm API, Toyobo/Takara/Thermo manuals). (`kuma_core/kuro/annealing.py`, `kuma_core/kuro/polymerase.py`, `kuma_core/kuro/resources/polymerase_profiles.json`, `python-core/sidecar_kuro/handlers/design.py`, `python-core/sidecar_kuro/models.py`, `src/components/widgets/resultTableColumns.tsx`, `docs/2026-07-16-annealing-ta-rules-verified.md`)

---
## v0.13.16 (In-app automatic updates)

### Added
- v0.13.16.0: Kuma can now **update itself in place**. When a newer signed release is detected, the update dialog offers **Update now**, which downloads the platform artifact, verifies its Ed25519 signature against the key embedded in the app, installs it, and relaunches — no manual installer step. Windows (NSIS), macOS, and Linux AppImage are fully automatic; Debian `.deb` has no updater artifact and falls back to opening the release page. Signing uses a self-generated Tauri updater key (not a paid code-signing certificate), so the free/unsigned distribution policy is unchanged and the SmartScreen guidance still applies. (`src-tauri/tauri.conf.json`, `src-tauri/src/lib.rs`, `src-tauri/capabilities/default.json`, `src/lib/updateCheck.ts`, `src/components/dialogs/UpdateAvailableDialog.tsx`, `.github/workflows/build.yml`, `scripts/gen-latest-json.mjs`)

---
## v0.13.15 (MAME Activity runs independently on layout + GC)

### Changed
- v0.13.15.0: MAME **Build EVOLVEpro input** no longer forces all four files. Layout + GC alone now produce a valid activity table for a first-round primary screen, marked **Provisional**; supplying the Agilent rep-batch (3-replicate re-measurement of positives) and the previous-round EVOLVEpro rank file upgrades the result to **Confirmed** (authoritative replicates merged over the primary screen, with per-variant mismatch QC preserved). Each pipeline step stays independently runnable and the result badge states the confidence level. The existing four-file confirmation workflow is unchanged. (`kuma_core/mame/activity/build_evolvepro_input.py`, `python-core/sidecar_mame/models.py`, `python-core/sidecar_mame/handlers/activity.py`, `src/types/mame/build_evolvepro_input.ts`, `src/components/mame/panels/BuildEvolveproInputPanel.tsx`, `src/locales/*.json`)

---
## v0.13.14 (KURO structure-accuracy guard for 3D selection)

### Fixed
- v0.13.14.0: KURO now uses AlphaFold Cα coordinates for structural-diversity and Pareto-3D selection only when the loaded structure exactly covers the reference sequence (identity or a clean substring; terminal tags/truncations are fine, interior substitutions are not). A near-but-not-exact structure would place coordinates on the wrong residues and silently corrupt selection; such cases now fall back to 1-D sequence distance with a status notice. Domain diversity is unaffected (sequence-based) and the benchmark comparison deliberately keeps both 1-D and 3-D arms. (`kuma_core/kuro/interface.py`, `python-core/sidecar_kuro/handlers/misc.py`, `src/store/slices/inputSlice.helpers.ts`)

---
## v0.13.13 (KURO ESMFold de-novo structure prediction)

### Added
- v0.13.13.0: The KURO 3D panel can predict a structure directly from the reference sequence via ESMFold (EMBL-EBI ESMAtlas) when no UniProt accession is available, enabling the 3D viewer, reference-frame dispersion, and pLDDT/variant/domain overlays for novel or synthetic constructs (≤400 residues). AlphaFold-by-accession remains the primary source; active/binding-site overlays require an accession and are hidden for ESMFold. (`kuma_core/kuro/esmfold.py`, `kuma_core/kuro/dispersion.py`, `python-core/sidecar_kuro/handlers/external.py`, `src/components/panels/Selection3DPanel.tsx`)
---
## v0.13.12 (KURO reference-sequence domains, guided tours, update checks, runtime fixes)

### Added
- v0.13.12.0: KURO **Scan sequence** annotates protein domains directly from the loaded reference sequence via EMBL-EBI InterProScan (after external-service consent), so domain coordinates match KURO mutation positions instead of UniProt accession numbering. Results cache by sequence SHA-256; reference-frame `refDomains` drive selection/benchmark while accession-frame `domains` stay dedicated to AlphaFold 3D coloring. (`kuma_core/kuro/domains.py`, `python-core/sidecar_kuro/handlers/external.py`, `src/store/slices/diversitySlice.ts`, `src/components/panels/InputPanel/UniprotSearch.tsx`)
- v0.13.12.0: New projects show a skippable spotlight tour of navigation and Kuro; Mame guidance appears separately on first entry. **Skip all tours** persists per project; `Esc` closes only the current tour; **Help → Show Guided Tour** replays it. Existing projects are never interrupted. (`src/components/dialogs/GuidedTour.tsx`, `src/components/dialogs/ProjectTourCoordinator.tsx`)
- v0.13.12.0: Kuma checks GitHub for a newer published release at startup and recommends it only when strictly newer; **Help → Check for updates** performs a real version check. Network failures never block startup. (`src/lib/updateCheck.ts`, `src/components/dialogs/UpdateAvailableDialog.tsx`)

### Fixed
- v0.13.12.0: **Export PNG** now has the binary file-write capability (`fs:allow-write-file`), reports save success/failure via toast, and no longer rejects the Tauri `fs.write_file` command. (`src-tauri/capabilities/default.json`, `src/components/panels/Selection3DPanel.tsx`)
- v0.13.12.0: The sequence viewer now draws domain bands from reference-frame domains so bands align with the loaded sequence; 3D residue spheres use a consistent opaque style to remove the 3Dmol ambiguous-opacity warning; title-only dialogs opt out of a missing description; an embedded favicon prevents the default `/favicon.ico` 404. (`src/components/widgets/SequenceViewer.tsx`, `src/components/panels/Selection3DPanel.tsx`, `index.html`)

---
## v0.13.11 (MAME single-step Activity, KURO 3D viewer background)

### Changed
- v0.13.11.0: MAME **Activity Data** is now a single step (3) that stacks Ingest, Merge, and Export in one scrollable view; the former 3.1 Ingest / 3.2 Merge & Export split is removed and the legacy `activity.mergeExport` id redirects to it. (`src/store/mame/slices/mameSubSteps.ts`, `src/components/mame/steps/ActivityStepView.tsx`, `src/components/mame/layout/MameWorkflowRail.tsx`, `src/components/mame/layout/MameAppLayout.tsx`, `src/locales/*.json`, `docs/mame/*`)

### Improved
- v0.13.11.0: the KURO 3D viewer defaults to a white background, and the Dark toggle now applies live (no reload). (`src/components/panels/Selection3DPanel.tsx`)

---

## v0.13.10 (KURO 3D surface + PNG export fixes)

### Fixed
- v0.13.10.0: the KURO 3D viewer **Surface** toggle now works in the packaged app. 3Dmol computes the molecular surface in a `blob:` Web Worker, which the app CSP blocked (no `worker-src`); the CSP now allows `worker-src 'self' blob:`, and surface generation degrades gracefully with a notice if a host webview still blocks workers. (`src-tauri/tauri.conf.json`, `src/components/panels/Selection3DPanel.tsx`, `src/locales/*.json`)
- v0.13.10.0: the KURO 3D viewer **Export PNG** button now saves a file. The Tauri webview ignores programmatic `<a download>`, so the export now uses the Tauri save dialog and writes the PNG via the fs plugin. (`src/components/panels/Selection3DPanel.tsx`)

---

## v0.13.9 (KURO dispersion structure-frame fix, release checksums)

### Fixed
- v0.13.9.0: KURO 3D dispersion no longer drops all positions ("N position(s) could not be mapped to the structure") when the structure loads but the UniProt FASTA fetch fails. The accession-frame sequence is now derived from the fetched AlphaFold/PDB structure itself (falling back to the UniProt FASTA only when the structure carries no sequence), so dispersion works whenever the structure is available. (`kuma_core/kuro/alphafold.py`, `kuma_core/kuro/dispersion.py`, `tests/test_g001_backend.py`)

### Improved
- v0.13.9.0: GitHub releases now attach a `SHA256SUMS.txt` for every installer and append Windows SmartScreen "Unknown publisher" guidance (More info → Run anyway), checksum-verification steps, and a macOS Gatekeeper note to the release body; a matching troubleshooting page is added. (`.github/workflows/build.yml`, `.github/release-footer.md`, `docs/troubleshooting/windows-smartscreen.md`, `docs/troubleshooting/index.md`)

---

## v0.13.8 (KURO 3D panel polish + packaged-sidecar dispersion fix)

### Improved
- v0.13.8.0: the KURO Candidate 3D structure analysis panel now explains itself inline — the Structural Dispersion card, its null-distribution histogram, and each metric row carry `?` help toggles; the histogram marker uses `P1`/`P96` percentile notation instead of `1%ile`; the metric is relabeled "Observed percentile vs random"; and a Color legend under the viewer maps every color (domain / pLDDT backbone, y_pred variant spheres, active-site sticks, binding-site spheres) to its meaning, adapting to the current coloring mode. (`src/components/panels/Selection3DPanel.tsx`, `src/locales/*.json`)
- v0.13.8.0: the Color legend rows are clickable toggles that show/hide each 3D layer (variant spheres, active-site sticks, binding-site spheres) while the backbone stays always-on; the standalone Interface checkbox is folded into the legend, and the panel is reordered to toolbar → 3D viewer → legend → Structural Dispersion → tables so toggle/coloring changes are visible in the viewer immediately. (`src/components/panels/Selection3DPanel.tsx`, `src/locales/*.json`)
- v0.13.8.0: corrected the mislabeled "Interface" overlay to "Binding site" across the viewer, legend, table column, and hover label — the magenta spheres are UniProt `Binding site` (ligand/cofactor/metal-binding) residues, not a protein-protein interface. (`src/components/panels/Selection3DPanel.tsx`, `src/locales/*.json`, `docs/kuro/05-output.md`)
- v0.13.8.0: documented that the 3D dispersion, pLDDT, and active/binding overlays are interpretation/QC aids, not candidate-selection filters — low-confidence or disordered residues are not auto-excluded from the mutation set, and EVOLVEpro y_pred ranking remains the sole selection authority. (`docs/kuro/05-output.md`)

### Fixed
- v0.13.8.0: the KURO 3D dispersion compute no longer fails in the packaged sidecar with `[Errno 2] No such file or directory: '..._MEI.../Bio/Align/substitution_matrices/data/BLOSUM62'`. The reference→accession position mapper now uses `PairwiseAligner` with explicit match/mismatch scoring instead of loading Biopython's loose `BLOSUM62` data file, which PyInstaller does not bundle into the temp extraction dir. (`kuma_core/kuro/interface.py`, `tests/test_g001_backend.py`)

---

## v0.13.7 (KURO Current-Selection 3D Analysis)

### Added
- v0.13.7.0: the KURO Output step gains a collapsible Current-Selection 3D Analysis panel that embeds a 3Dmol viewer (collapsed by default to avoid eager 3Dmol loading) and reports the spatial dispersion of the selected residue positions. (`src/components/panels/Selection3DPanel.tsx`, `src/lib/selection3d.ts`, `src/components/steps/OutputStepView.tsx`, `src/store/slices/diversitySlice.ts`)
- v0.13.7.0: the backend adds a stdlib-only 3D dispersion null-model (`compute_round_dispersion`, mean pairwise C-alpha distance versus random sampling) plus UniProt active/binding-site fetch in the accession frame, wired through the kuro dispatcher. (`kuma_core/kuro/dispersion.py`, `kuma_core/kuro/uniprot_features.py`, `python-core/sidecar_kuro/dispatcher.py`, `python-core/sidecar_kuro/handlers/external.py`, `python-core/sidecar_kuro/models.py`)
- v0.13.7.0: the panel strings are localized across all 10 locales, and `3dmol@^2.5.5` is added as a dependency. (`src/locales/*.json`, `package.json`)

---

## v0.13.6.1 (What's New automation)

### Added
- v0.13.6.1: the What's New dialog is auto-generated from `CHANGELOG.md` (`pnpm gen:whatsnew`); `sync:check` now fails the build when the generated module drifts or when the latest CHANGELOG section does not match `package.json`'s version. (`scripts/gen-whatsnew.mjs`, `src/components/dialogs/whatsNew.generated.ts`, `package.json`)

### Fixed
- v0.13.6.1: corrected the Kuro Export All BOM label to "UTF-8 BOM (Excel compatibility)" across all 10 locales. (`src/components/steps/ExportFormatSelector.tsx`, `src/locales/*.json`)
- v0.13.6.1: aligned KURO wizard step bodies and MAME file-picker field widths. (`src/components/steps/WizardContainer.tsx`, `src/components/mame/panels/FileField.tsx`)

---

## v0.13.5 - v0.13.6 (macOS SSL fix, MAME sample-data UX)

### Fixed
- v0.13.5: outbound HTTPS (Kuro UniProt search, AlphaFold, EBI BLAST, ESM) failed on the packaged macOS app with `CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate`. macOS OpenSSL does not read the Keychain and the frozen app has no build-machine CA store, so `ssl.create_default_context()` had no trust anchors. All external requests now route through a shared certifi-backed SSL context (`certifi.where()`, bundled by PyInstaller `hook-certifi`), identical on Windows, macOS, and Linux. Windows and Linux were unaffected because their OS CA stores are present on the target. (`kuma_core/shared/net.py`, `python-core/sidecar_kuro/core.py`, `kuma_core/kuro/alphafold.py`, `kuma_core/kuro/esm_embeddings.py`, `pyproject.toml`)
- v0.13.6: MAME step 1.1 "Generate Barcode Package" no longer requires the output directory to live inside the project root (it failed with `output_dir must be inside project_root`). `mame_context.json` stores paths relative when the output is inside the project root (portable) and absolute when outside, and the loader resolves both. (`kuma_core/mame/ingest/barcode_package.py`, `src/lib/mame/detectProjectFiles.ts`)

### Added
- v0.13.6: loading sample data populates a precomputed analysis result (`samples/mame/sample_analysis_result.json`, serialized from the real demux/consensus/verdict/health pipeline) so the Per-plate verdict breakdown renders instead of showing "Setup incomplete". (`python-core/scripts/generate_mame_sample_result.py`, `src/store/mame/slices/analysisSlice.ts`)
- v0.13.6: loading sample data seeds the Build EVOLVEpro Input form (layout / GC data / Agilent rep-batch / previous EVOLVEpro) from the bundled `06`/`08`/`09`/`10` sample xlsx files; fields already set by the user are preserved. (`src/store/mame/slices/analysisSlice.ts`, `src/lib/mame/buildEvolveproFormStorage.ts`, `src/components/mame/panels/BuildEvolveproInputPanel.tsx`)

---

## v0.13.3.1 - v0.13.4.0 (native MinKNOW run-folder ingestion, auto-updater removal, CI quality gates, i18n parity)

### Added
- v0.13.4.0: MAME `analyze` auto-detects a raw MinKNOW run folder (a directory containing `fastq_pass/`) and orchestrates demux → consensus internally, so a pre-demuxed consensus directory is no longer required. There is no new RPC: the pre-demuxed consensus path and the standalone `mame.run_combinatorial_demux` RPC are unchanged, and the `{R}_{F}` well-naming contract is preserved. (`kuma_core/mame/ingest/run_pipeline.py` `is_minknow_run_dir`/`ingest_run_folder`, `python-core/sidecar_mame/handlers/analyze.py`, `python-core/sidecar_mame/models.py` `DemuxParamsBase`/`AnalyzeRawRunParams`, `src/types/mame/models.ts`, `src/store/mame/slices/inputSlice.ts`, `src/hooks/mame/useMameSidecar.ts`)
- v0.13.4.0: raw-run analyze emits two-phase progress (demux 0–50, analyze 50–100) carrying a `stage` field, so the UI shows one demux→analyze flow from a single `analyze` call with a dedicated `MAME_RAWRUN_RPC_TIMEOUT_MS`; the consensus-directory path keeps its byte-identical 0–100 progress with no `stage` key. (`python-core/sidecar_mame/handlers/analyze.py`, `src/store/mame/slices/inputSlice.ts`, `src/hooks/mame/useMameSidecar.ts`)
- v0.13.4.0: CI gains a `quality-gates` job (pytest / `tsc --noEmit` / `sync:check` / `i18n:check`) that gates the release build, plus a new `mame-analyze-run-folder` cross-layer sync group keeping the demux params identical across Pydantic, TypeScript, and the dispatcher. (`.github/workflows/build.yml`, `.cross-layer-sync.json`)
- v0.13.4.0: all 10 locales brought to full key parity with `i18n-lint` hardening; UI locales and the Kuro/MAME screens now load on demand (dynamic `import()` + `React.lazy`/`Suspense`), trimming the initial JS bundle. (`src/locales/*.json`, `scripts/i18n-lint.mjs`, `src/lib/i18n.ts`, `src/screens/MainShell.tsx`)

### Removed
- v0.13.4.0: the Tauri auto-updater is removed — the frontend `src/lib/updater.ts`, the Cargo dependency, the updater capability, the `lib.rs` plugin registration, and the About-dialog wiring are all gone, and the Check-for-updates menu entry is repurposed to the release page. (`src/lib/updater.ts` deleted, `src-tauri/Cargo.toml`, `src-tauri/capabilities/default.json`, `src-tauri/src/lib.rs`, `src/components/layout/SharedAboutDialog.tsx`)

### Fixed
- v0.13.3.2: corrected an EVOLVEpro numeric overflow and four stale test expectations.
- v0.13.3.3: the verdict window note now reflects the real window instead of a hardcoded ±5, `compute_T3` is de-duplicated, and the SDM parse fallback is logged instead of failing silently.

---

## v0.13.0.1 - v0.13.3.0 (MAME verdict depth gate, analyze progress, resume hardening, export guards, macOS build)

### Fixed
- v0.13.0.1: MAME verdict depth gate uses the consensus header `depth=N` (real read depth) instead of the consensus FASTA file size; the file-size check is demoted to a fallback that fires only when `depth=N` is absent, and `CompareParams.min_read_count` now defaults to 30. Previously every well was flagged `LOWDEPTH` because a gene-length-fixed consensus FASTA (~1.8KB, identical across same-amplicon wells) could never reach the raw-read `min_file_size_kb=50` floor. (`kuma_core/mame/compare/verdict.py`, `kuma_core/mame/models.py`)
- v0.13.1.0: MAME analyze emits per-record sub-progress and runs a 30s keep-alive heartbeat, fixing the ETA stalling near 60% and the 300s "no response" deadlock popup on long but healthy analyze runs. (`kuma_core/mame/pipeline.py` `run_analyze`, `python-core/sidecar_mame/handlers/analyze.py`)
- v0.13.2.4: the resume orphan guard detects stray `.fa`/`.fas` files (not only `.fasta`) via a shared `CONSENSUS_FILE_PATTERNS`; resumed demux runs seed `n_input_reads`/`n_unassigned` from completion markers so totals no longer undercount or go negative. (`kuma_core/mame/ingest/stage_marker.py`, `kuma_core/mame/ingest/fasta_parser.py`, `python-core/sidecar_mame/handlers/demux.py`)
- v0.13.2.6: MAME resume/skip now also covers the raw_run path (`run_combinatorial_demux_per_nb`), not only `handle_demux_and_filter`. Re-running raw_run on a folder that has completion markers skips already-finished native barcodes instead of re-demuxing everything. (`kuma_core/mame/ingest/combinatorial_demux.py`, `kuma_core/mame/ingest/stage_marker.py`)

### Added
- v0.13.2.1: MAME step 2.1 (demux/consensus) writes are atomic (temp file + `os.replace`), each native-barcode group writes a `.demux_consensus_complete.json` completion marker, and a rerun skips groups whose marker matches the on-disk inventory. An asymmetric consumer guard fails fast on a present-but-invalid marker while still loading legacy or externally-sorted directories that have no marker. (`kuma_core/shared/atomic_write.py`, `kuma_core/mame/ingest/stage_marker.py`, `python-core/sidecar_mame/handlers/demux.py`, `kuma_core/mame/ingest/fasta_parser.py`)
- v0.13.2.2: overwrite confirmation for the MAME Janus mapping, Run report, and Barcode package exports; the Barcode package confirms at the `design/` directory level. (`src/components/mame/dialogs/JanusMappingDialog.tsx`, `RunReportDialog.tsx`, `src/components/mame/panels/BarcodeSetupPanel.tsx`, `src/lib/overwriteConfirm.ts`)
- v0.13.3.0: `max_consensus_n_fraction` is adjustable from the MAME analyze parameter panel (default 0.0, strict by default). (`src/components/mame/panels/ParameterPanel.tsx`, `src/store/mame/slices/inputSlice.ts`)
- v0.13.2.5: macOS minimap2 is compiled from source in CI (`make arm_neon=on aarch64=on`, pinned v2.30) and bundled into the macOS sidecar, mirroring the Windows MinGW step; previously the macOS build had no minimap2 source and failed at `build_sidecar.py`. (`.github/workflows/build.yml`)

---

## v0.12.1.0 – v0.12.3.4 (minimap2 CLI cross-platform)

In-process `mappy` 정렬기를 사이드카에 번들된 `minimap2` CLI 로 교체. mappy 는 Windows wheel 이 없어 MAME `raw_run` 이 Windows 에서 실패했음.

### Changed
- `kuma_core/mame/ingest/align.py`: `align_reads`/`align_reads_multi` 가 `minimap2` 바이너리를 subprocess 로 호출하고 SAM 을 파싱, 동일한 `Alignment` dataclass 반환. 바이너리는 `KURO_MINIMAP2` → 사이드카 `_MEIPASS/bin` → PATH 순으로 해석.
- reverse-strand `q_st`/`q_en` 를 원본 read 좌표로 환산, soft/hard clip 을 `Alignment.cigar` 에서 제거하여 mappy 와 일치(실 ONT 데이터에서 consensus byte-identical 검증).
- `build_sidecar.py` / `mame-sidecar.spec`: PyInstaller `--add-binary` 로 플랫폼별 `minimap2` 를 `_MEIPASS/bin/` 에 번들.
- `.github/workflows/build.yml`: 사이드카 빌드 전 vendor 채우기. Linux/macOS 는 `scripts/vendor-minimap2.py` 로 공식 바이너리 다운로드, Windows 는 MSYS2/MinGW 정적 빌드(`make LIBS="-Wl,-Bstatic -lm -lz -lpthread -Wl,-Bdynamic"`) + `ldd` 가드로 비정적 바이너리 거부.
- `.github/workflows/ci.yml`: `python-tests` 에 minimap2 제공(Linux/macOS). `tests/mame/conftest.py` 는 바이너리 부재 시 MAME 테스트 skip(Windows leg).

### Removed
- `pyproject.toml` 의 `mappy` 의존(main + `mame-raw` extra).

### Added
- `NOTICE-bundled.md`: minimap2(MIT)·zlib 서드파티 고지, 번들 `NOTICE.md` 에 병합.

---

## v0.11.0.0 (PR-B: Legacy cleanup)

Remove legacy sort_barcode pipeline and Trim Adapters UI fields.
Aporva-style alignment-based combinatorial demux becomes canonical.

### Removed
- `kuma_core.mame.ingest.sort_barcode`: sliding/edlib read-sorting algorithm
  (`sort_barcode_run`, `_sort_one_nb`, `_hamming_prefix_window_in_head`,
  `_hamming_suffix_window_in_tail`, `_FWD_SEARCH_WINDOW_BP`, `_EDIT_DIST_RATIO`,
  `SortBarcodeResult`, `_hamming_suffix_window`)
- `python-core/sidecar_mame/handlers/sort_barcode.py`: RPC handler
- `sort_barcode_run` method from dispatcher `_METHODS` and `_ASYNC_METHODS`
- `src/types/mame/sort_barcode.ts`: TypeScript type file
- `RawRunParams.minBarcodeScore`, `linkedTrim`, `revPrimerUniversal` state fields
- Trim Adapters, Universal Rev Primer, Min Barcode Score UI fields (9 keys x 10 locales)

### Changed
- `sort_barcode.py` retained as barcode xlsx parser module only
  (`parse_combinatorial_barcodes`, `parse_sample_map`, `_make_well_filename`,
  `_nb_to_sort_barcode_name`)
- `models.py`: removed `_check_pr_b_fields_deferred` validator;
  `sample_map_xlsx` and `kuro_xlsx` params now accepted without error
- `.cross-layer-sync.json`: removed `mame-sort-barcode` and
  `mame-dispatcher-sort-barcode` groups

---

## v0.10.3.0 (PR-A: combinatorial demux frontend)

Add combinatorial demux RPC and UI.

- ParameterPanel Advanced section (coverageFraction, editDistRatio, chimeraSplit)
- `mame.run_combinatorial_demux` RPC wired to `runAnalysis` in `inputSlice`
- `selectCanRun` updated for raw_run mode validation

---

## v0.10.2.0

Chimera-aware demux for concatenated nanopore reads.

---

## v0.10.1.0

Add combinatorial_demux pipeline for 96-well amplicon screening.
