# KURO Update Notes — v0.9.5 → v0.9.29

[한국어](UPDATE-NOTES.ko.md) | **English**

Released: 2026-03-26

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
