# kuma — primer design (Kuro) + NGS verification (Mame)

[한국어](README.ko.md) | **English**

`kuma` packages two subtools into one Tauri desktop app:

- **Kuro** — *Kernel for Upstream Recombination Oligodesign.* Batch SDM primer design from Gibson Assembly templates.
- **Mame** — *Mutagenesis Assessment & Microplate Export.* Oxford Nanopore NGS verdict on which clones carry the intended mutations.

Design primers in the Kuro tab, run wet-lab + sequencing, then switch to the Mame tab to verify which clones carry the intended mutations.

![kuma overview](docs/kuro_overview.png)

Project folders keep Kuro design output and Mame verification linked across the weeks-long gap between ordering oligos and reading sequencing output. A hidden `__kuma_meta__` sheet in every Kuro-exported xlsx lets Mame auto-recognise the source project when the file is dropped back in.

---

## Tabs

### Kuro — SDM primer design

Given a mutation list (plain text / EVOLVEpro CSV / MULTI-evolve CSV) and a template sequence (GenBank / SnapGene), Kuro automatically designs SDM primer pairs using the overlap extension method.

- **EVOLVEpro / MULTI-evolve CSV input**: Load EVOLVEpro (`variant`, `y_pred`) or MULTI-evolve (`mutation`, `property_value`) output CSV — column format is auto-detected. Sorts by score descending → auto-selects the configured number of variants. Optional **position diversity** filter limits mutations per amino acid position (uses Grantham 1974 distance as tie-breaker when scores are within 2%). Optional **domain diversity** distributes selections across protein structural domains (auto-fetched from InterPro/Pfam or manual input). Optional **Pareto diversity** maximizes position spread via MODIFY-style fitness-diversity co-optimization. **σ-Adaptive Pool**: enter EVOLVEpro Round and Round size to automatically calibrate the candidate pool width and entropy weight based on cumulative data (K = 0.50→0.25, entropy = 0.30→0.15 across rounds 1–5+)
- **Batch mutation parsing**: Mutation list in `Q232A` format → automatic codon position calculation + WT codon validation
- **Codon strategy selection**: Choose between Min. changes (fewest base changes from WT) or Optimal (E. coli-optimized codon)
- **Overlap upstream design**: Overlap region is placed immediately upstream of the mutation codon (EVOLVEpro convention)
- **Polymerase profile selector**: Seven built-in profiles (Benchling, Taq, Phusion, Q5, KOD, DreamTaq, TAKARA_GXL), each with Tm method, salt concentration, DNA concentration, and GC range calibrated to the manufacturer manual. Custom profiles can be created via the Custom Polymerase dialog and are persisted at `~/.kuma/kuro/custom_polymerases.json`. Selecting a profile immediately updates Tm targets and GC range in the UI
- **Tm calculation**: SantaLucia 1998 nearest-neighbor model; salt/DNA/divalent conditions vary per polymerase profile (e.g. Phusion HF 222 mM monovalent, Q5 150 mM monovalent + 2000 nM DNA). Default Tm targets: Fwd 62°C, Rev 58°C, Overlap 42°C — adjustable in Advanced Options
- **Progressive Tm tolerance**: Starts at ±0.5°C for Fwd/Rev independently, expanding by ±0.5°C per step (up to ±3.0°C)
- **GC% range**: Default 40-60% (adjustable in Advanced Options). Primers outside range receive a penalty
- **Primer length limit**: Optional Fwd/Rev min/max length constraint (adjustable in Advanced Options)
- **Hairpin / Homodimer check**: Secondary structure check via primer3 calc_hairpin/calc_homodimer. Displays Tm and dG (kcal/mol)
- **AlphaFold 3D distance**: Pareto diversity uses real Cα Euclidean distance from AlphaFold DB predicted structures instead of 1D sequence position distance. Fetched automatically after UniProt accession entry; cached at `~/.kuma/kuro/embeddings/{accession}_ca.json`. Falls back to 1D position distance when the structure is unavailable
- **Benchmark framework**: Compare Kuro selection (Pareto/Domain) vs Random vs Top-N on fitness landscapes. Metrics: hit rate, mean fitness, position coverage
- **Synthesis quality score**: Oligo synthesis difficulty assessment (0-100) based on IDT/Twist guidelines. Penalizes homopolymer runs, GC-rich stretches, dinucleotide repeats, and extreme GC content
- **Sequence Map**: Collapsible SVG linear CDS map with mutation positions, domain regions, and density histogram for cluster detection
- **Column sorting**: All result columns sortable (including y_pred and synthesis score). Plate map export respects current sort order
- **Candidate comparison and swap**: Click a primer sequence to open a candidate comparison popover
- **Custom primer evaluation**: Enter a sequence directly in the candidate popover → Tm, GC%, hairpin, and off-target are calculated immediately
- **Failed mutation retry**: Click a failed mutation → adjust Tm/GC%/length/tolerance → re-design → select from candidates. The retry popover offers a one-click **Use suggestion** button that pre-fills median Tm, observed GC/length range, and tol ±5°C derived from primers that already succeeded in the same run
- **Tm tolerance setting**: User-configurable Tm tolerance ±°C (range 0.5–10.0, step 0.5, default 3.0) in Advanced Options. Cascade rescue stages add delta on top of this base value. Recommended 2–5°C
- **Position Rescue**: Mode-aware multi-stage cascade when a primer design fails.
  - **Top-N + Fill-on-failure ON** → 4-stage relaxation only (length → +GC → +mild Tm → strong), position fixed. Badges `🎯¹` length / `🎯²` +GC / `🎯³` +mild Tm / `🎯⁴` strong
  - **Pipeline + Fill-on-failure ON** → 6-stage: ① same-position alternate variant (`↻¹`) → ② different-position substitution (`↻²`) → ③–⑥ same 4-stage relaxation
  - **Fill-on-failure OFF** → failed mutations remain failed; no automatic retry or substitution runs
  - Legacy pool cascade (`↻ cascade`) and auto-relax (`⚡ relaxed`) still applied by the backend before frontend cascade
  - Stage counters displayed in Design Report
- **Auto-rescue failed mutations**: When enabled (default on), triggers the cascade above according to selection mode. When off, failed mutations remain as-is
- **Off-target detection**: Automatic detection of non-specific binding on the template sense/antisense strand
- **96-well Plate Map**: Linked Fwd/Rev plate. Multi-plate slide for >96 mutations. Synchronized with table sort order
- **Echo 525 / JANUS export**: Liquid handler mapping export as XLSX workbook. Echo: 384-well source plate layout + transfer list. JANUS: Fwd/Rev 96-well rack layout + transfer list. CSV also supported

### Mame — NGS screening verdict

Given a Kuro-exported `expected_mutations.xlsx`, a reference FASTA, and Oxford Nanopore barcode-mode consensus FASTA files, Mame produces per-barcode mutation verdicts and a 96-well Final Excel export.

- **Consensus FASTA ingest**: Barcode-mode output from Nanopore basecaller. Mock fixtures included at `tests/mame/fixtures/`.
- **6-class verdict**: Each barcode classified into one of six outcomes (exact match, partial, off-target, WT retained, no coverage, ambiguous).
- **3-replicate best pick**: Among triplicate barcodes, the best-scoring clone is selected.
- **96-well Final Excel export**: Column-major 96-well layout with verdict per well. Synchronized with Kuro's plate map ordering.
- **Single-view workbench**: Input files panel, parameter panel (mode, CDS end, cutoffs), verdict table with NB01/NB02/NB03/ALL filter, 96-well map with colorblind-safe toggle.
- **Substitution support**: Phase 1 focuses on single-residue substitutions. Deletion / insertion reserved for later.

## Selection Strategies (Kuro, EVOLVEpro / MULTI-evolve mode)

When loading a scored CSV (EVOLVEpro or MULTI-evolve), Kuro applies the configured selection strategy to choose which mutations to design primers for. Strategies are independent checkboxes and can be combined.

| Strategy | Description | When to use |
|----------|-------------|-------------|
| **Top-N by score** | Select the top N mutations ranked by predicted fitness score (y_pred / property_value descending). N = max primers setting (default 95). | Default ranking. Use when predicted fitness is the only criterion. |
| **Position diversity** | Limit the number of mutations per amino acid position (default: 1 per position). When two variants at the same position score within 2%, the more conservative substitution (lower Grantham 1974 distance) is preferred. Applied as a pre-filter before other strategies. | Prevent over-sampling at mutational hot spots. |
| **Domain diversity** | Allocate mutation quota proportionally (by domain length) or equally across protein structural domains. Domains are auto-fetched from InterPro/Pfam via UniProt accession, or entered manually. | Ensure coverage across all functional regions. |
| **Pareto diversity** | Greedy maximin position selection: iteratively pick the mutation whose position is farthest from all already-selected positions. Maximizes spatial spread across the protein sequence. | Prevent clustering of mutations in a narrow region. Inspired by the MODIFY approach (Ding et al., *Nature Communications*, 2024). |
| **Entropy-guided** (β) | Blends per-position Shannon entropy of the y_pred distribution (weight 0.3) into the Pareto score. Positions where many mutations score similarly are prioritised. | Escape local optima. Requires Pareto diversity to be enabled. |

**Reference**
- Ding D, Shaw AY, Sinai S, et al. Protein design using structure-predicted residue preferences and sequence-predicted fitness. *Nature Communications*, 15:6729 (2024). PMID:39080249 — MODIFY: Pareto fitness-diversity co-optimization

## Project workflow

On first launch kuma asks for a **projects root** folder (default `~/Documents/kuma`). All projects live inside as folders:

```
<projects_root>/
└── Sample_42/
    ├── kuma.project.json          # project metadata (schema v1)
    ├── design/
    │   ├── workspace.kuro.json    # Kuro workspace (same format as legacy .kuro.json)
    │   └── expected_mutations.xlsx # carries hidden __kuma_meta__ sheet
    └── analysis/
        ├── consensus/             # drop Nanopore consensus FASTAs here
        └── verdict.xlsx           # Mame output
```

The `stage` field (draft / design_complete / analyzing / done) is derived automatically from file presence. Scratch mode (open a single `.kuro.json` without creating a project) remains supported for compatibility with legacy Kuro workspaces.

## Installation

Download the latest installer from [Releases](https://github.com/gyuminlee-repo/kuma/releases).

- **Windows**: `kuma_x.x.x_x64-setup.exe` (NSIS)
- **macOS**: `kuma_x.x.x_aarch64.dmg`
- **Linux**: `.deb` + `.AppImage`

### Developers — `pnpm setup` instead of `pnpm install` on Windows

On Windows, `pnpm install` may fail with `EACCES` / `EBUSY` on the first run when Defender or an IDE file watcher locks files in `node_modules`. Use the wrapper script:

```powershell
pnpm setup
```

`scripts/safe-install.mjs` runs `pnpm install` with `package-import-method=copy` (hardlink locks bypassed) and retries up to three times on retryable errors. macOS and Linux fall back to a plain `pnpm install` with retries.

If three attempts still fail, the script prints a guide (close IDE, add Defender exclusion, or wipe `node_modules`).

### macOS — first-launch Gatekeeper notice

kuma ships with ad-hoc code signing only (no paid Apple Developer ID). The first launch shows an "unidentified developer" warning. If the dialog instead says **"is damaged and can't be opened"**, the file picked up the quarantine bit during download — clear it once:

```bash
xattr -cr /Applications/kuma.app
```

Then bypass Gatekeeper one of these ways:

1. Finder → right-click (Control-click) `kuma.app` → **Open** → **Open**
2. System Settings → Privacy & Security → scroll to the kuma entry → **Open Anyway**

Subsequent launches require no further action.

## Usage

**Kuro tab**
1. **Help → Load Sample Data** to load examples, or:
2. Load a sequence file (GenBank `.gb` / SnapGene `.dna`)
3. Verify the target CDS in the Target Gene dropdown (auto-selected)
4. Enter mutations (text / EVOLVEpro CSV / MULTI-evolve CSV)
5. Select codon strategy (Min. changes / Optimal)
6. *(Optional)* Adjust Tm, GC%, length in Advanced Options
7. Click **Design Primers**
8. File → Export Excel (writes `design/expected_mutations.xlsx` with `__kuma_meta__` embedded)

**Mame tab** (after wet lab + sequencing)
1. **Help → Load Sample Data** to load examples, or:
2. Drop Nanopore consensus FASTAs into the input panel
3. Reference FASTA + `expected_mutations.xlsx` (auto-suggested if the active project has them)
4. Set CDS end / mode / cutoffs
5. **Run** → verdict table + 96-well plate map
6. **Export** → final xlsx

Dropping a Kuro-exported xlsx into Mame while a different project is active triggers the "load source project?" dialog (matched via `__kuma_meta__ → project_id`).

## Activity Data Integration (v0.2.7)

KUMA now connects the complete ALE cycle: Kuro designs primers for Round N, wet lab runs the mutations, NGS genotyping identifies which clones succeeded, activity assay measures functional improvement, and a single "Handoff" click feeds the activity data back into Kuro for Round N+1.

### Workflow

```
1. KURO Design  →  primer list for Round N mutations
2. Wet lab       →  site-directed mutagenesis + expression
3. MAME NGS      →  per-clone genotype verdict (6-class)
4. Activity assay→  plate-reader / fluorescence measurement
5. MAME Activity →  load long-format CSV; compute fold_change / log2_fc
6. EVOLVEpro export → variant + activity xlsx for next round (`[Variant, activity]` 2-column, `89W` short notation)
7. Round Handoff →  1-click: create Round N+1, load EVOLVEpro output into Kuro (short-form variants auto-converted via protein ref_seq)
8. Repeat        →  Kuro designs Round N+1 from updated scores
```

### Long Format CSV Input

The activity loader expects a **long format** CSV (or Excel) file with one measurement per row:

| Column | Type | Description |
|---|---|---|
| `plate_id` | string | Plate identifier, e.g. `P01` |
| `well_id` | string | Well address in A01–H12 format |
| `value` | float | Raw measurement value |
| `replicate_idx` | int | Replicate index (1-based); same well × same replicate_idx = one measurement |

WT wells are declared in `plate_meta.json`:

```json
{
  "plates": [
    { "plate_id": "P01", "wt_wells": ["A01", "A12", "H01", "H12"] }
  ]
}
```

Fold change and log2_fc are computed relative to the mean WT value on each plate. The log2_fc value maps directly to EVOLVEpro `y_pred`.

### Round Entity

Each ALE round is tracked as a `Round` entity in the workspace (schema v0.3). A round holds:
- `round_n`: sequential round number (1-based)
- `status`: `design` → `sequencing` → `activity` → `exported`
- `plate_meta`: WT well layout for that round
- Links to the Kuro workspace and MAME NGS results for that round

Workspace files from schema v0.2 and earlier are **not automatically migrated**. Export your design data before upgrading from v0.2.6 or earlier.

### v0.3 xlsx pipeline (v0.2.8+)

xlsx-native readers cover the inputs the wet-lab actually produces: `mutants-well position.xlsx`, Agilent GC-FID raw exports (standard / rep-batch), and EVOLVEpro xlsx files. `kuma_core/mame/activity/evolvepro_xlsx.py:detect_format` auto-dispatches.

`mame.activity.merge_for_evolvepro` (v0.2.9.0) replaces the legacy merge for EVOLVEpro export: it joins activity to genotype, runs `merge_replicates_priority` (authoritative-prefer with mismatch flag), executes the label-swap guard, and surfaces `replicate_stats` plus `export_blocked` in the response. The 5/12 demo continues to use the legacy `activity.merge` path; the v0.3 button "EVOLVEpro용 병합 (v0.3)" lives next to it in the panel and never replaces it.

The IspS WT amino acid sequence is auto-loaded from `fixtures/ispS.fa` (Populus alba ispS CDS, AB198180.1) via BioPython translate when `ref_seq` is omitted — no UI plumbing required for IspS rounds.

---

## Architecture

Tauri v2 + React 19 shell with two Python sidecars (kuro-sidecar, mame-sidecar) spawned lazily on first tab activation. The Rust side owns project CRUD, config, and sidecar lifecycle. Both sidecars share `kuma_core.shared` utilities — config paths, logging, JSON-RPC error format, and `kuma_core.shared.sidecar` helpers (`JsonRpcWriter`, bounded crash-log append, private config dir, path validation).

```
+-------------------------+
| Tauri shell (React)     |
| ├─ Home / Onboarding    |
| └─ MainShell [Kuro|Mame]|
+-------------------------+
       ↓ sidecar_rpc(kind, method, params)
+----------------+   +----------------+
| kuro-sidecar   |   | mame-sidecar   |
| (PyInstaller)  |   | (PyInstaller)  |
+----------------+   +----------------+
```

## Common Frontend Standards

Kuro and Mame conform to the **Common Frontend Standards charter** (`docs/standards/common-frontend-standards.md`, v1.1 stable) — 22 categories covering recovery, observability, input guards, error UX, output persistence, settings, UI safety, accessibility, versioning, telemetry, build, reproducibility (`run.json`), long-running jobs (queue + OS notification + sleep inhibit), data integrity (input/output SHA-256, sidecar binary hash, schema dry-run migration), onboarding, local diagnostics, cross-platform, partial success, performance guardrails, citation/licensing, multi-workspace, graceful shutdown. PrimerBench applies the same charter through its Phase A-E rollout.

## License

[GPL v2](LICENSE)
