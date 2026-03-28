# KURO Update Notes — v0.9.5 → v1.0.0

[한국어](UPDATE-NOTES.ko.md) | **English**

Released: 2026-03-28

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
