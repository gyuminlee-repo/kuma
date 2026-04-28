# kuma — primer design (Kuro) + NGS verification (Mame)

[한국어](README.ko.md) | **English**

Desktop app that integrates **Kuro** (batch SDM primer design) and **Mame** (Oxford Nanopore NGS screening verdict) into a single workflow. Design primers in the Kuro tab, run wet-lab + sequencing, then switch to the Mame tab to verify which clones carry the intended mutations.

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
- **Failed mutation retry**: Click a failed mutation → adjust Tm/GC%/length/tolerance → re-design → select from candidates
- **Position Rescue**: When a primer design fails, automatically attempts same-position backup variants from the EVOLVEpro pool (Pool Cascade), then widens Tm tolerance (±5.0°C) and GC range (±5%) (Auto-Relax). Rescue statistics displayed in Design Report
- **Fill on failure**: When enabled (off by default), automatically fills the requested mutation count from extra candidates when some mutations fail
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
- **macOS**: `kuma_x.x.x_x64.dmg`
- **Linux**: `.deb` + `.AppImage`

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

## Architecture

Tauri v2 + React 19 shell with two Python sidecars (kuro-sidecar, mame-sidecar) spawned lazily on first tab activation. The Rust side owns project CRUD, config, and sidecar lifecycle. Both sidecars share `kuma_core.shared` utilities (config paths, logging, JSON-RPC error format).

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

## License

[GPL v2](LICENSE)
