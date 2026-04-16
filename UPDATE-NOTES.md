# KURO Update Notes — v0.9.5 → v1.33.0

[한국어](UPDATE-NOTES.ko.md) | **English**

---

## v1.33.0 (2026-04-16)

### CI hardening

- **`verify-ci` gate**: Release build jobs now block until the CI workflow succeeds on the tagged commit. Prevents release artifacts from building off a red CI run
- **`ui-smoke` job**: Playwright headless browser test added to CI. Builds the Vite frontend and runs `pnpm run smoke:ui` against Chromium
- **`sidecar-package-check` job**: Builds the PyInstaller sidecar on CI (Ubuntu) and verifies the output binary exists — catches packaging regressions before release
- **`pyproject.toml` added to version-sync check**: CI now validates that `pyproject.toml` version matches `package.json`, `tauri.conf.json`, and `Cargo.toml`
- Replaced explicit `pip install primer3-py==... biopython==...` with `pip install -e '.[build]'` in CI for consistency with local dev setup

### Security

- **Removed SSL certificate bypass** in `kuro/alphafold.py`: The `_ssl_ctx()` helper that set `CERT_NONE` / disabled `check_hostname` has been removed. AlphaFold API and PDB download calls now use the system default SSL context

### EVOLVEpro — domain quota overflow fix

- `domain_aware_select()` in `kuro/evolvepro.py` now reduces excess quotas when the sum exceeds `top_n`. Previously, `domain_quota_min` enforcement could push the total above the requested count. Excess is trimmed from the most-over-quota domain first (proportional/equal strategy aware), breaking ties by original quota order

### Sidecar — concurrent design safety

- **Per-job cancel events**: Replaced the module-level `_cancel_event` with a per-job `threading.Event` allocated by `_begin_design_job()`. `cancel_design` RPC now returns `{"cancelled": true, "active_design": bool}` indicating whether an active job was actually cancelled. Prevents one request from cancelling an unrelated later job
- **`design_sdm_primers` moved to `_ASYNC_METHODS`**: Design now runs in a background thread, keeping the JSON-RPC loop responsive during long primer searches
- **Race-free state clearing**: Previous design state is cleared only after the new design job slot is reserved, avoiding a window where state could be zeroed while a cancelled job still ran
- **Contact email config**: `KURO_CONTACT_EMAIL` environment variable (or `contact_email` key in `~/.kuro/config.json`) controls the email used in crash reports and external API calls. Falls back to `None` if unset
- **`ca_coords_accession` tracking**: `SidecarState` now stores the accession for cached Cα coordinates so stale structure data can be detected without re-fetching

### Frontend

- **IPC stdout buffering** (`src/lib/ipc.ts`): Replaced `line.split("\n")` with `drainChunkLines` / `flushBufferedLine` helpers that handle partial JSON-RPC lines emitted by the sidecar across multiple stdout chunks. Fixes rare JSON parse errors on large progress payloads
- **SequenceViewer memoization**: `DomainLayer`, `ScaleLayer`, `DensityLayer` extracted as `React.memo` sub-components, reducing re-render cost on zoom or pan
- **diversitySlice generation counters**: `domainFetchGeneration`, `uniprotSearchGeneration`, `structureFetchGeneration` per-request counters prevent stale domain/UniProt/structure responses from overwriting newer state; `structureAccession` field tracks the accession of the loaded structure

### Developer

- **Version normalization**: `1.32.03` → `1.32.3` across `package.json`, `tauri.conf.json`, `Cargo.toml`, and `pyproject.toml` (removed leading zeros in patch segment)
- `pyproject.toml` `kuro` library version now tracks the app version (was `0.9.28`)

---

## v1.32.0 (2026-04-10)

### SDM primer length spec — aligned to slide reference

Recalibrated primer length parameters against the PI presentation deck (`260408_KURO_발표자료_퀄리티/`) hmk2 Slide 1 STEP 1:

- **overlap**: 8–18 bp (Tm target 42°C)
- **Forward primer total**: 17–39 bp (Tm 62°C, structure `[overlap] + [3 bp mutant codon] + [downstream ≥4 bp]`)
- **Reverse primer total**: 19–27 bp (Tm 58°C)

### Polymerase profile as single source of truth

- Added `overlap_len`, `fwd_len_min/max`, `rev_len_min/max` fields to `PolymeraseProfile`
- All 7 built-in profiles (Benchling, Taq, Phusion, Q5, KOD, DreamTaq, TAKARA_GXL) populated with the slide spec
- `design_single_sdm` and `design_sdm_primers` now resolve length defaults from the profile when `None` is passed
- Pydantic sidecar params default to `None`, so workspace JSONs without `overlap_len` fall back to the profile
- `DesignSdmPrimersParams.overlap_len` hard-capped at `ge=8, le=18` (enforces slide spec). `RetryFailedParams` and `EvaluatePrimerParams` keep `le=40` so rescue exploration and legacy-primer evaluation still work.

### Sliding-window off-target detection (PrimerBench port)

- New `check_offtarget_sliding()` in `kuro/sdm_engine.py` — a direct port of PrimerBench `check_primer_binding()`
- Enumerates every contiguous sub-sequence `[min_length=15, primer_len]` of the primer and scans both template strands for exact matches
- Catches **internal-window hits** (15-mers trimmed from both 5' and 3' ends) that the existing 3'-anchor method (`check_offtarget`) cannot detect
- New `OffTargetHit.truncation_type` field: `full` / `5prime` / `3prime` / `internal` / `3prime_anchor`
- 5 new tests covering internal match, self-hit exclusion, antisense detection, and full-length matching

### UI / CLI / fixture fan-out

- `ParameterPanel.tsx`, `exportSlice.ts` (workspace load/reset), `CandidatePopover.tsx`, `designSlice.ts` initial state — stale fallbacks cleared
- CLI `--overlap`, `--fwd-len-*`, `--rev-len-*` default to `None` (profile-driven)
- `kuro/sdm_engine.py:444` magic literal `35` replaced with `rev_len_max` parameter
- `fixtures/generate_sample_data.py` plus 4 test fixtures updated

### Breaking change / migration

- Primers generated with 1.31.x fall outside the new length envelope (20 bp overlap, >39 bp fwd, >27 bp rev). Re-running the same input will produce a different result distribution.
- Workspace JSONs with `overlap_len: 20` now raise a 422 `ValidationError` — edit the file or re-save from the UI.

---

## v1.30.1 (2026-04-06)

### Polymerase Profile Corrections — Sync with primerbench v2.17.2

- Recalibrated Tm/salt parameters for 4 built-in polymerases against manufacturer manual values:
  - **Taq**: `breslauer+schildkraut` → `santalucia+owczarzy`; salt_monovalent 50→51 mM, salt_divalent 0, dna_conc 800 nM
  - **Phusion**: salt_correction `owczarzy` → `schildkraut`; salt_monovalent 50→222 mM (Thermo HF buffer), salt_divalent 0, dna_conc 500 nM
  - **Q5**: salt_monovalent 50→150 mM (NEB Q5 buffer), salt_divalent 0, dna_conc 250→2000 nM
  - **DreamTaq**: `breslauer+schildkraut` → `santalucia+owczarzy`; salt_divalent 0, dna_conc 800 nM, max_size 25→30
- Added **TAKARA_GXL** profile: opt_tm 58°C, santalucia+owczarzy, max_tm_diff 5.0

---

## v1.30.0 (2026-04-06)

### UniProt Search — Auto-Select Top Result

- UniProt search now automatically selects the top-ranked candidate on completion, regardless of identity score
- Previously, auto-selection only triggered on 100% identity; candidates below that threshold required manual selection
- Status message now shows the actual identity percentage from the search result (e.g. `auto-selected P12345 (87.3% identity)`) instead of a hardcoded label

### Default Parameter Changes

- `primerLenEnabled` default: `false` → `true` (primer length constraints active by default)
- `fillOnFailure` default: `false` → `true` (fill on failure active by default)
- Same defaults applied in workspace load fallback (`exportSlice`)

### UI — Sidebar Flex Overflow Fix

- Added `overflow-x-hidden` to left sidebar container to prevent horizontal overflow
- Added `min-w-0` to `flex-1` select elements in ParameterPanel (Polymerase, Codon strategy)

---

## v1.29.0 (2026-04-04)

### Echo / JANUS Mapping Export — XLSX with Plate Layout

- Echo 525 and JANUS liquid handler mapping exports now produce XLSX workbooks instead of CSV, matching the lab reference format (`040.mapping_files_echo/`)
- **Echo** workbook (2 sheets):
  - **layout**: 384-well source plate (Fwd odd rows + Rev even rows interleaved) + 96-well PCR destination plate
  - **Echo mapping file**: transfer list (Source/Dest Plate, Well, Transfer Vol)
- **JANUS** workbook (2 sheets):
  - **layout**: Fwd 96-well plate + Rev 96-well plate + PCR mixture destination plate (single sheet)
  - **primer_mapping file**: transfer list (Asp/Dsp Rack, Posi, volume)
- CSV format remains supported when the user explicitly selects `.csv` extension

### UniProt Search — Auto-Select Top Result

- UniProt search now automatically selects the top-ranked candidate on completion, regardless of identity score
- Previously, auto-selection only triggered on 100% identity; candidates below that threshold required manual selection
- Status message now shows the actual identity percentage from the search result (e.g. `auto-selected P12345 (87.3% identity)`) instead of a hardcoded label

### Bug Fix — Domain Exclusion Not Filtering Disabled Positions

- When specific domains were disabled in the UI, mutations at those positions were incorrectly classified as "linker" and included in the selection — primers were still designed for them
- Root cause: the frontend sent only `activeDomains` to the backend; positions in disabled domains fell outside all domain boundaries and were placed in the linker bin
- Fix: new `excluded_ranges` parameter sent from the frontend to `load_evolvepro_csv()` → `domain_aware_select()`. Positions matching any excluded range are dropped before domain/linker assignment
- `ExcludedRange` Pydantic model added to `LoadEvolveproParams`

---

## v1.28.0 (2026-04-03)

### Position Rescue — Pool Cascade + Auto-Relax

**Pool Cascade**
- When a primer design fails, the system automatically attempts alternative variants at the same amino acid position from the EVOLVEpro pool. The `pool_variants` list (all variants in the effective pool before position/diversity filters) is returned by `load_evolvepro_csv()` and sent as `rescue_pool` in the design request
- Frontend computes the rescue pool by subtracting intended mutations from pool variants

**Auto-Relax**
- If pool cascade does not rescue a failed mutation, the system retries the original mutation with widened parameters: Tm tolerance ±5.0°C (default ±3.0°C), GC range ±5% (floor 20%, ceiling 80%)
- `design_single_sdm()` now accepts a `tol_max` parameter (default 3.0) instead of a hardcoded value

**Backend**
- `_build_mutation()` and `_build_profile()` helper functions extracted from `handle_retry_failed()` for reuse in the rescue loop
- `DesignSdmPrimersParams` model extended with `rescue_pool: list[str]` and `auto_relax: bool` fields
- Design response includes `rescue_stats` (pool_cascade/auto_relax counts, positions_attempted, pool_variants_tried) and `rescued_mutations` (details per rescue including penalty and tolerance_used)
- Auto-relax constants derived from SantaLucia (1998) nearest-neighbor Tm prediction s.e. (~1.0-1.5°C): `_RELAX_TOL_DELTA = 2.0°C`, `_RELAX_GC_DELTA = 5 pp`, clamped to IDT-recommended 20-80% range
- Rescued mutations prioritized in maxPrimers cap to prevent loss when fill-on-failure is active

**UI Feedback**
- Design Report shows a "Position Rescue" section with position coverage ratio, pool variants tried count, and average penalty comparison (rescued vs normal primers with 1.5x warning threshold)
- Result table displays rescue badges: green `↻ Q232A` for pool cascade (showing original mutation), amber `⚡ relaxed` for auto-relax, with per-mutation penalty
- Status bar includes rescue count (e.g. "95/95 designed | Tm: 93/95 | 3 rescued")

**Tests**
- `TestPoolVariants` (2 tests): pool_variants returned correctly; pareto pool size within expected range
- `TestAutoRelaxTolMax` (1 test): `tol_max` parameter accepted with correct default

---

## v1.27.0 (2026-04-03)

### UX Simplification — Progressive Disclosure + σ-Adaptive Pool

**Pipeline UI: Progressive Disclosure**
- `DiversityOptions` rebuilt with basic/advanced split. Step 1 shows only the on/off toggle (position cap hidden); Step 2 shows toggle + linker handling + domain list + UniProt search; Step 3 shows toggle + distance mode badge only
- New **Round** section: "EVOLVEpro Round" and "Round size" inputs drive σ-adaptive pool automatically. Computed K and entropy weight are displayed live (e.g. `Auto K=0.50 / entropy=0.30`)
- **Advanced** accordion (hidden by default) exposes: position cap, domain strategy / overlap policy / min quota, distance mode radio, manual pool K slider, manual entropy weight override
- Benchmark Defaults and Workspace settings separated into distinct sections below the pipeline

**σ-Adaptive Pool (EVOLVEpro Round)**
- Pool threshold is computed from cumulative data points (Round × Size): `threshold = anchor − K × σ`, where σ is the standard deviation of all y_pred scores and anchor is the top-N-th ranked score
- K and entropy weight are derived from estimated model quality ρ (Spearman, literature-based): K = 0.50 / 0.40 / 0.30 / 0.25 and entropy weight = 0.30 / 0.25 / 0.20 / 0.15 for cumulative ≤ 96 / ≤ 192 / ≤ 384 / 385+ data points
- `evolvepro_round` and `round_size` parameters added to `LoadEvolveproParams` and `load_evolvepro_csv()`. When `evolvepro_round > 0`, manual `pool_multiplier` and `entropy_weight` are overridden by the computed values
- Workspace save/load persists `evolveproRound` and `roundSize`; defaults: round = 1, size = 96

**Same-Position Tie-Break (Grantham 1974)**
- Position diversity filter now uses Grantham distance as a tie-breaker when two variants at the same position score within 2% of each other — preferring the more conservative (lower Grantham distance) amino acid substitution
- Equal Grantham distance → alphabetical order for deterministic selection
- Grantham 1974 distance table (190 amino acid pairs, *Science* 185:862–864) added to `kuro/evolvepro.py`

**Tests**
- `TestSigmaAdaptivePool` (5 tests): ρ boundary values, K / entropy weight mapping, σ-adaptive pool size and auto-override
- `TestGranthamTieBreak` (7 tests): conservative substitution preference, score gap threshold, alphabetical fallback, `max_per_position` respect

---

## v1.24.1 (2026-04-01)

### Polymerase Selection + Custom Profiles

- Added a Polymerase selector to `ParameterPanel`; KURO now sends the selected profile to the sidecar instead of hardcoding `Benchling`
- Selecting a polymerase immediately updates the UI defaults for Tm targets and GC range from that profile
- Added `get_polymerase_details` and `save_custom_polymerase` JSON-RPC methods
- Added a Custom Polymerase dialog for creating or editing user-defined profiles
- Custom polymerases are persisted at `~/.kuro/custom_polymerases.json` and are reloaded automatically on the next app start
- Added registry persistence test coverage for custom polymerases

---

## v1.22.0 (2026-03-30)

### Primer Length Defaults — KOD One Minimum + Experimental Range

- UI default minimum raised to **22 bp** (Fwd and Rev) to match KOD One PCR Master Mix official recommendation (22–35 bp, Tm >63°C)
- UI default maximum: Fwd 45 bp, Rev 35 bp — covers the observed experimental range (강혜민 IspS SDM: F 19–38 bp, R 18–32 bp) with buffer
- Python layer (`sdm_engine.py`) retains 18 bp defaults for unconstrained designs and test compatibility; the 22 bp minimum is enforced only when the UI Primer Length constraint is enabled
- **Help tooltip added** to the "Primer Length" section header in Advanced Options: click `?` to view KOD One specs, experimental range (n=165), and a note that KURO primer lengths include the overlap region
- The `title` attribute (hover-only) replaced by a click-to-toggle `HelpTip` component — consistent with the Step 1–3 help buttons added in v1.21.0

---

## v1.21.0 (2026-03-30)

### Advanced Settings Help Tooltips

- Added `?` click-to-toggle help buttons to pipeline Step 1–3 settings in `DiversityOptions.tsx`
- Tooltips cover: position cap, domain diversity strategy, Pareto diversity (with AlphaFold status), and entropy-guided selection
- Replaces hidden `title` attribute tooltips which were not discoverable on touch/keyboard

### Semver Fix

- Version strings corrected from two-part (`1.21`) to three-part (`1.21.0`) semver in `package.json`, `tauri.conf.json`, and `Cargo.toml`
- Tauri and Cargo both require `MAJOR.MINOR.PATCH` format; two-part strings caused build failures
- Push skill updated (step 3.5) to auto-sync all three version files when committing

---

## v1.20.0 (2026-03-30)

### CI Fix — pydantic Missing from Build

- Added `pydantic>=2.0` to the pip install step in `.github/workflows/build.yml`
- Without this, the PyInstaller sidecar bundle raised `ModuleNotFoundError: No module named 'pydantic'` at startup
- `build_sidecar.py` already included `--collect-all pydantic`; the CI workflow was the missing piece

---

## v1.19.0 (2026-03-30)

### AlphaFold Cα 3D Distance — Replaces ESM-2

- Pareto diversity selection now uses real 3D structural distance from AlphaFold DB instead of ESM-2 cosine distance in language-model embedding space
- New `kuro/alphafold.py`: fetches AlphaFold DB predicted structure via REST API (`alphafold.ebi.ac.uk/api/prediction/{accession}`), parses Cα coordinates from PDB ATOM records, and computes normalized Euclidean distance. No ML dependencies (pure stdlib)
- Cached at `~/.kuro/embeddings/{accession}_ca.json` (same directory as before)
- Sidecar RPC renamed: `fetch_esm_embedding` → `fetch_structure`. Response changed: `{success, residues}` instead of `{success, length, dimension}`
- AlphaFold structure is fetched automatically after UniProt auto-match or manual accession entry
- Fallback to 1D position distance when AlphaFold structure is unavailable (protein not in DB or offline)
- `esm_embeddings.py` retained for reference but no longer used by the main pipeline
- DiversityOptions UI: "ESM-2" badge and status replaced with "AlphaFold" badge

### UniProt Search — AlphaFold Availability Badge

- Each UniProt candidate in the search results now shows an "AF" badge (indigo) when an AlphaFold predicted structure is available for that accession
- Availability is checked in parallel (up to 5 threads) immediately after BLAST/text search completes. Cache hits return instantly; first check has a 5-second timeout per accession
- Hover tooltip updated to include "AlphaFold structure available" when applicable
- New `check_structure_available()` helper in `kuro/alphafold.py` — checks local cache first, then queries AlphaFold DB API without downloading the full PDB

### Bug Fix — Fill on Failure (EVOLVEpro mode)

- In EVOLVEpro mode, `loadEvolveproCsv` was always called with `top_n = maxPrimers`, so `mutationText` had exactly `maxPrimers` lines. The fill buffer (`sendCount = maxPrimers × 1.5`) had nothing to fill from — the feature was silently inoperative
- Fixed: when Fill on Failure is enabled, the CSV is reloaded with `top_n = sendCount` before design, providing buffer candidates from the EVOLVEpro pool. After design completes, the list is restored to `maxPrimers`
- `loadEvolveproCsv` now accepts an optional `topNOverride` parameter

---

## v1.18.0 (2026-03-30)

### UniProt Search — TrEMBL Coverage

- Added UniProt REST text search (`gene_exact:<name>`) as a third step after BLAST, covering both Swiss-Prot and TrEMBL entries. Previously, only Swiss-Prot was reachable via EBI BLAST (`uniprotkb_swissprot`), so TrEMBL entries such as `A0PFK2` were not found
- BLAST database remains `uniprotkb_swissprot` (unchanged); text search supplements it when BLAST returns zero hits or misses TrEMBL

### UX — UniProt BLAST In-Progress Banner

- A blue spinner banner "UniProt BLAST search in progress… (Step 2 available after)" now appears in the Sequence Input panel immediately after a file is loaded. The banner disappears when the search completes. Previously, the search ran silently and users had no indication that Step 2 was pending

### Bug Fixes

- **DesignReport infinite loop**: Applied `useShallow` to the multi-field Zustand selector in `DesignReport.tsx`. The previous inline object selector returned a new reference on every render, causing a React `Maximum update depth exceeded` crash when the Radix UI Dialog `Presence` component re-rendered
- **`shell:allow-kill` missing**: Added `shell:allow-kill` to `src-tauri/capabilities/default.json`. Without this, the sidecar kill-on-cancel command was silently blocked by Tauri's permission system
- **semver patch**: Version strings corrected from `1.17` to `1.17.0` in `package.json`, `tauri.conf.json`, and `Cargo.toml`. Both Cargo and Tauri require three-part semver

### ESM-2 Local Inference

- `fair-esm` and `torch` are now the recommended installation for Pareto structural distance. Install: `pip install fair-esm torch --index-url https://download.pytorch.org/whl/cpu` (CPU) or `pip install fair-esm torch` (GPU). The remote ESM Atlas endpoint (`api.esmatlas.com`) returns 403 and is no longer used
- ESM-2 is intentionally not bundled in the sidecar exe (torch adds 500MB–2GB, PyInstaller compatibility issues). The fallback to 1D position distance is the default for distributed builds

---

## v1.0.0 (2026-03-28)

### Stable Release
- Version bump from v0.9.39 to v1.0.0 — no feature changes
- All three core workflows verified:
  1. GenBank → manual mutations → primer design → Excel export
  2. FASTA + EVOLVEpro CSV → diversity selection → primer design → IDT order
  3. FASTA + MULTI-evolve CSV → combinatorial variants → batch design
- 3-OS CI/CD green (Ubuntu/Windows/macOS)
- 191 tests passing

---

## v0.9.39 (2026-03-28)

### Design Review Fixes
- **IPC timeout**: `sendRequest` now has a configurable timeout (default 60s). Prevents permanent UI hang when sidecar is unresponsive
- **BLAST cancel-aware polling**: Replaced blocking 3s sleep with 0.5s intervals that check the cancel event, allowing cancellation during UniProt BLAST search
- **Zustand type safety**: Unified all 3 store slices with `AppState` generic type. Removed 52 unsafe `as unknown as` / `as Partial<>` casts
- **ESM embedding lifecycle**: Clearing `esm_embedding` when template changes to prevent cross-protein contamination in Pareto analysis
- **ESM-2 model caching**: Module-level model cache avoids reloading the ~150MB model on every inference call
- **CSV reload debounce**: Pipeline option toggles now debounce the CSV reload RPC by 300ms, eliminating burst requests
- **Shared utilities**: Extracted duplicate `formatError` helper to `src/lib/utils.ts`. Added `src/store/types.ts` for combined `AppState` type
- **Release checklist**: Documented updater pubkey (empty) and BLAST email (hardcoded) as release blockers
- **Sidecar spawn race condition fix**: `onReady` handler is now registered before `command.spawn()` to prevent the `ready` notification from being dropped when sidecar starts faster than the await yields

---

## v0.9.37 (2026-03-28)

### UniProt Search — BLAST-based
- Replaced gene name text search with EBI NCBI BLAST API (blastp against UniProt Swiss-Prot)
- Protein sequence is directly BLASTed — works correctly for FASTA files without gene annotations
- Fixed URL encoding bug that caused organism filter to silently fail (space in organism name → `InvalidURL`)
- Error details now surfaced to UI instead of being silently swallowed

### FASTA Header Parsing
- New `_parse_fasta_header()` extracts gene name and organism from NCBI and UniProt header formats
- `_detect_orfs()` now receives parsed gene/organism info
- `.fna` extension support added (backend + frontend file dialog)

### ESM-2 Local Inference
- Switched from ESM Atlas API (now 403 Forbidden) to local `fair-esm` + `torch` inference
- Model: `esm2_t12_35M_UR50D` (35M params, 480D, ~150MB)
- Graceful fallback to 1D position distance when `fair-esm` is not installed
- ESM embedding now properly connected through the full selection pipeline:
  `handle_load_evolvepro_csv` → `load_evolvepro_csv` → `pareto_diversity_select` / `domain_aware_select`
- Previously, ESM embedding was fetched but never passed to the selection algorithms

### Pipeline Defaults
- All pipeline steps enabled by default: `pipelineMode`, `positionDiversityEnabled`, `domainDiversityEnabled`, `paretoDiversityEnabled`, `entropyWeightEnabled` = `true`
- Users see step descriptions + progress instead of toggle switches

### Design Report Modal
- New `DesignReport.tsx` modal dialog auto-opens after primer design completes
- Shows: pipeline summary, primer success/failure stats, Tm distribution, domain allocation stats, failed mutations
- Uses existing Radix Dialog primitive

### Package Manager Migration
- npm → pnpm (`packageManager: "pnpm@10.33.0"` in `package.json`)
- Scripts, `tauri.conf.json`, GitHub Actions CI/build workflows updated
- `pnpm-lock.yaml` generated via `pnpm import`

### Fixture Data
- Domain-enriched EVOLVEpro CSVs generated for `ispS.fa` (75% in-domain) and `pSHCE-dmpR.fa`
- Multi-evolve batch CSVs with verified WT amino acid positions
- Removed stale `evolvepro_round*.csv` and `multi_evolve_batch.csv`

---

## v0.9.36 (2026-03-27)

### Try Sample Button
- "Try sample →" button added to Input panel header
- Loads bundled sample GenBank + EVOLVEpro CSV automatically via `resolveResource`
- `tauri.conf.json`: `"resources": ["../samples/**"]` added for production bundling

### Entropy-Guided Selection (β)
- New diversity strategy: blends per-position Shannon entropy (weight 0.3) into Pareto greedy maximin score
- Positions where many mutations score similarly (high uncertainty) are prioritised
- Requires Pareto diversity to be active; toggled via "Entropy-guided" checkbox (β badge) in Pipeline Step 3
- Backend: `_position_entropy()` helper + `entropy_weight` param in `evolvepro.py` and `sidecar_main.py`

### Documentation
- README / USER-GUIDE (EN + KO): Entropy-guided row added to Selection Strategies table, Pareto + Entropy-guided combination example, Try sample step in Usage

---

## v0.9.35 (2026-03-27)

### ESM-2 Structural Distance
- Pareto diversity now uses ESM-2 cosine distance when embedding is available, falling back to 1D position distance
- ESM Atlas API integration: auto-download per-residue embeddings by UniProt accession
- Local cache at `~/.kuro/embeddings/` (JSON format)
- InputPanel shows "(ESM-2)" badge when structural distance is active

### Benchmark Framework
- `kuro/benchmark.py`: simulate_selection, evaluate_selection, run_benchmark
- Compare KURO (Pareto/Domain) vs Random vs Top-N on any fitness landscape
- Metrics: hit rate, mean fitness, position coverage, unique positions
- `handle_run_benchmark` RPC for frontend integration

### Other
- Remove M. extorquens AM1 from codon tables (4 species: E. coli, B. subtilis, S. cerevisiae, H. sapiens)
- Fix Tauri updater API (`Builder::new().build()`)
- 191 tests (was 160)

---

## v0.9.33 (2026-03-27)

### Deployment Infrastructure
- **Tauri auto-updater**: `tauri-plugin-updater` v2, GitHub Releases endpoint, "Check for Updates" in About dialog
- **Crash reporting**: Python sidecar logs to `~/.kuro/crash.log` (FIFO 50 entries), frontend ErrorBoundary saves to localStorage, "Copy Crash Log" button
- **CI cargo check**: Rust compilation verification added to GitHub Actions (parallel with pytest and typecheck)

---

## v0.9.32 (2026-03-27)

### Multi-Organism Codon Tables
- 4 species: E. coli K-12, B. subtilis 168, S. cerevisiae, H. sapiens
- `CodonTableRegistry` with JSON resource files, organism dropdown in ParameterPanel

### IDT/Twist Order Export
- `export_idt_csv()` and `export_twist_csv()` in plate_mapper.py
- File menu: "Export IDT Order..." / "Export Twist Order..."

### UniProt Auto-Search
- `GeneInfo` extended: organism, translation, uniprot_accession from GenBank `/db_xref`
- Auto-trigger on sequence load, candidate dropdown with identity % badges
- CDS DNA auto-translation for FASTA files (enables sequence comparison)

### File Drag and Drop
- Tauri `onDragDropEvent` for sequence (.gb, .dna, .fa) and CSV files
- Blue ring visual feedback during drag

### Keyboard Shortcuts
- Ctrl+S (save), Ctrl+E (export), Ctrl+D (design), Ctrl+O (open)
- Menu hints, input-safe suppression

---

## v0.9.31 (2026-03-27)

### Quick Wins
- **ErrorBoundary**: crash → "Something went wrong. Click to reload" screen
- **Sidecar failure banner**: red "Sidecar connection failed" message in StatusBar
- **ParameterPanel tooltips**: all settings have title attributes
- **Clipboard copy**: copy icon on primer sequences (click to copy, checkmark feedback)
- **USER-GUIDE**: selection strategy decision guide, codon limitation note, troubleshooting section

### Code Refactoring
- `kuro/evolvepro.py` extracted from sidecar (326 lines, reusable from CLI)
- CLI: 11 new parameters (tm targets, gc range, primer length, codon strategy)
- `appStore.ts`: 872 lines → 3 Zustand slices (input/design/export)
- `ResultTable.tsx`: 1273 lines → 573 + 4 popover files

---

## v0.9.30 (2026-03-27)

### Domain Diversity Fix
- `top_n` was hardcoded to 9999 in `loadEvolveproCsv`, making domain quotas effectively unlimited
- Fixed to use `maxPrimers` (default 95) for proper proportional/equal allocation
- Added Selection Strategies section to README with descriptions, use cases, and references

---

## v0.9.29 (2026-03-26)

### New Features
- **Synthesis quality score**: Each primer now receives a synthesis difficulty score (0-100) based on IDT/Twist guidelines. Penalizes: homopolymer runs (4+), GC-rich stretches (6+), dinucleotide repeats (8+), extreme GC content (<30% or >70%). Shown in the Syn column with color coding (green/amber/red). Hover the cell for Fwd/Rev breakdown
- **Sequence Map viewer**: Collapsible SVG linear CDS map showing mutation positions. Green ticks = designed, red = failed. Density histogram overlay highlights clustering. Domain regions shown with quota labels (selected/quota with warning for under-filled domains)
- **y_pred column**: EVOLVEpro mode shows y_pred values in the result table. Sortable by clicking the column header
- **Design cancel**: Cancel button appears next to "Design Primers" during design. Kills the sidecar and respawns for clean state
- **Domain toggle**: Fetched domains are shown as checkboxes instead of deletable items. Toggle individual domains on/off while preserving the full list

### Selection Strategy
- **Independent checkboxes**: Top-N, Position, Domain, and Pareto diversity are now independent checkboxes that can be combined in any combination
- **Design-time sync reload**: Diversity settings are applied immediately before primer design, preventing race conditions where async CSV reload had not completed
- **Strategy required**: EVOLVEpro mode requires at least one strategy checkbox before designing
- **Domain diversity fix**: `top_n` was hardcoded to 9999, causing domain quotas to be effectively unlimited. Fixed to use `maxPrimers` (default 95), enabling proper proportional/equal allocation across domains

### Improvements
- **Fill on failure default OFF**: Changed from ON to OFF to prevent unexpected mutation substitution
- **Sidecar orphan prevention**: Parent process watchdog (5s interval) detects when Tauri dies and auto-exits the sidecar. Uses WaitForSingleObject (Windows) / os.kill (Unix)
- **Auto-reconnect**: If sidecar is not running when a request is made, it automatically spawns
- **Header tooltips**: All result table columns and the Sequence Map header show explanatory tooltips on hover
- **Modal accessibility**: ESC key close, auto-focus, role="dialog", aria-modal for all popovers

### Cross-platform
- **CI 3-platform matrix**: Tests run on ubuntu, windows, macos with Python 3.11/3.12
- **Encoding**: All file I/O uses explicit `encoding="utf-8"`
- **Build scripts**: Cross-platform sidecar kill (taskkill/pkill) and python/python3 auto-detection

### Developer
- **122 tests** (was 38): Added test_polymerase (19), test_codon_table (26), test_sidecar_rpc (31), test_synthesis_score (10), test_cancel_check (3)
- **`cancel_design` RPC**: Sets threading.Event to break the design loop gracefully
- **`design_sdm_primers` callbacks**: `on_progress(i, total, mutation_raw)` and `cancel_check()` parameters

---

## v0.9.27 and earlier

## Export

- **Excel List sheets now include Tm and codon data**: Fwd/Rev List sheets contain Tm, Tm_Overlap, WT_Codon, MT_Codon columns in addition to the existing Well, Primer Name, Sequence, Length, Mutation columns
- **Sort order reflected in export**: Any column sort applied in the result table is preserved in the Excel plate map output

## Parameters

- **Primer length limit**: New optional constraint in Advanced Options. Set Fwd/Rev min/max primer length. Default: Fwd 18-45 bp, Rev 18-30 bp
- **Fill on failure** (default ON): When some mutations fail primer design, KURO automatically sends extra candidates and fills the requested count from next-ranked mutations. Disable to attempt exactly the specified number without replacement
- **Mutations parameter = final success count**: The Mutations number now represents the target number of successful primer designs, not just the number of input mutations to attempt
- **Primer minimum length raised**: Default minimum primer length changed from 12 bp to 18 bp

## EVOLVEpro

- **Domain diversity**: Distributes Top-N variant selection across different protein structural domains via InterPro/Pfam annotation. Enter a UniProt accession to auto-fetch domain boundaries, or define them manually. Two allocation strategies: proportional (by domain length) and equal. Prevents high-scoring mutations from clustering in a single domain
- **Pareto diversity**: MODIFY-style fitness-diversity co-optimization. Greedy maximin algorithm maximizes position spread among selected variants, preventing nearby mutations from clustering. Usable alone or combined with domain diversity (applies within each domain)
- **Position diversity filter**: Optional checkbox limits the number of mutations per amino acid position. Prevents high-scoring mutations at the same position (e.g., Q10A, Q10L, Q10V) from dominating the selection. Adjustable max per position (default 1)
- All three diversity filters (Position, Domain, Pareto) are independent toggles — usable in any combination. All off = pure y_pred Top-N (default)

## Result Table

- **All columns sortable**: Every column except Forward/Reverse Primer sequences can be sorted by clicking the column header. Hairpin (HP) column now supports sorting by worst Tm
- **Failed mutation display**: Failures are shown only for the user-intended mutations (top N). Buffer overflow failures are hidden. The Failed section shows "Failed (N/target)" format

## Failed Mutation Recovery

- **Retry with adjusted parameters**: Click a failed mutation tag → a popup opens with adjustable Tm targets, GC% range, primer length limits, and tolerance max. Click **Retry** to redesign only that mutation with custom parameters. Up to 10 candidates are shown sorted by penalty. Click **Select** to add to the result table
- **Manual input preserved**: The existing manual primer input feature is still available under "Or enter manually..." in the same popup

## UI

- **Advanced Options reorganized**: Labeled sections (Tm / GC% / Primer Length / Design) replace the previous flat list. Primer Length checkbox and inputs are compacted into fewer lines
- **Status messages improved**: Status bar shows success/target count, Tm condition met ratio, and failure count when applicable

## Developer

- **Auto version sync**: A post-commit git hook (`scripts/sync-version.sh`) automatically syncs `package.json`, `tauri.conf.json`, and `Cargo.toml` version numbers when the commit message matches the `vX.Y.Z:` pattern
- **New JSON-RPC API**: `retry_failed_mutation` — redesign a single failed mutation with custom Tm/GC/length/tolerance parameters, returning up to 10 candidates
