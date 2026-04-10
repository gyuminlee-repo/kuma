# KURO — Kernel for Upstream Recombination Oligodesign

[한국어](README.ko.md) | **English**

Desktop app for batch SDM primer design based on Gibson Assembly.

![KURO Overview](docs/kuro_overview.png)

https://github.com/user-attachments/assets/f95e65ca-22d2-4479-a06b-8dcd553571be

Given a mutation list (plain text / EVOLVEpro CSV / MULTI-evolve CSV) and a template sequence (GenBank / SnapGene), KURO automatically designs SDM primer pairs using the overlap extension method.

## Features

- **EVOLVEpro / MULTI-evolve CSV input**: Load EVOLVEpro (`variant`, `y_pred`) or MULTI-evolve (`mutation`, `property_value`) output CSV — column format is auto-detected. Sorts by score descending → auto-selects the configured number of variants. Optional **position diversity** filter limits mutations per amino acid position (uses Grantham 1974 distance as tie-breaker when scores are within 2%). Optional **domain diversity** distributes selections across protein structural domains (auto-fetched from InterPro/Pfam or manual input). Optional **Pareto diversity** maximizes position spread via MODIFY-style fitness-diversity co-optimization. **σ-Adaptive Pool**: enter EVOLVEpro Round and Round size to automatically calibrate the candidate pool width and entropy weight based on cumulative data (K = 0.50→0.25, entropy = 0.30→0.15 across rounds 1–5+)
- **Batch mutation parsing**: Mutation list in `Q232A` format → automatic codon position calculation + WT codon validation
- **Codon strategy selection**: Choose between Min. changes (fewest base changes from WT) or Optimal (E. coli-optimized codon)
- **Overlap upstream design**: Overlap region is placed immediately upstream of the mutation codon (EVOLVEpro convention)
- **Polymerase profile selector**: Seven built-in profiles (Benchling, Taq, Phusion, Q5, KOD, DreamTaq, TAKARA_GXL), each with Tm method, salt concentration, DNA concentration, and GC range calibrated to the manufacturer manual. Custom profiles can be created via the Custom Polymerase dialog and are persisted at `~/.kuro/custom_polymerases.json`. Selecting a profile immediately updates Tm targets and GC range in the UI
- **Tm calculation**: SantaLucia 1998 nearest-neighbor model; salt/DNA/divalent conditions vary per polymerase profile (e.g. Phusion HF 222 mM monovalent, Q5 150 mM monovalent + 2000 nM DNA). Default Tm targets: Fwd 62°C, Rev 58°C, Overlap 42°C — adjustable in Advanced Options
- **Progressive Tm tolerance**: Starts at ±0.5°C for Fwd/Rev independently, expanding by ±0.5°C per step (up to ±3.0°C)
- **GC% range**: Default 40-60% (adjustable in Advanced Options). Primers outside range receive a penalty
- **Primer length limit**: Optional Fwd/Rev min/max length constraint (adjustable in Advanced Options)
- **Hairpin / Homodimer check**: Secondary structure check via primer3 calc_hairpin/calc_homodimer. Displays Tm and dG (kcal/mol)
- **AlphaFold 3D distance**: Pareto diversity uses real Cα Euclidean distance from AlphaFold DB predicted structures instead of 1D sequence position distance. Fetched automatically after UniProt accession entry; cached at `~/.kuro/embeddings/{accession}_ca.json`. Falls back to 1D position distance when the structure is unavailable
- **Benchmark framework**: Compare KURO selection (Pareto/Domain) vs Random vs Top-N on fitness landscapes. Metrics: hit rate, mean fitness, position coverage
- **Synthesis quality score**: Oligo synthesis difficulty assessment (0-100) based on IDT/Twist guidelines. Penalizes homopolymer runs, GC-rich stretches, dinucleotide repeats, and extreme GC content
- **Sequence Map**: Collapsible SVG linear CDS map with mutation positions, domain regions, and density histogram for cluster detection. Hover over histogram bars to see mutation count per AA region
- **Column sorting**: All result columns sortable (including y_pred and synthesis score). Plate map export respects current sort order
- **Candidate comparison and swap**: Click a primer sequence to open a candidate comparison popover (clickable even with a single candidate). Manually swapped primers are highlighted in amber in the result table
- **Custom primer evaluation**: Enter a sequence directly in the candidate popover → Tm, GC%, hairpin, and off-target are calculated immediately
- **Failed mutation retry**: Click a failed mutation → adjust Tm/GC%/length/tolerance → re-design with modified parameters → select from candidates
- **Position Rescue**: When a primer design fails, automatically attempts same-position backup variants from the EVOLVEpro pool (Pool Cascade), then widens Tm tolerance (±5.0°C) and GC range (±5%) for still-failed mutations (Auto-Relax). Rescue badges shown in result table (green `↻` for pool cascade, amber `⚡` for auto-relax) and rescue statistics displayed in Design Report
- **Fill on failure**: When enabled (off by default), automatically fills the requested mutation count from extra candidates when some mutations fail
- **Off-target detection**: Automatic detection of non-specific binding on the template sense/antisense strand. Click OT `!!` to view a detailed popover with binding position, strand, and Tm
- **96-well Plate Map**: Linked Fwd/Rev plate. Multi-plate slide for >96 mutations (Plate N Fwd ↔ Plate N Rev). Synchronized with table sort order
- **Echo 525 / JANUS export**: Liquid handler mapping export as XLSX workbook. Echo: 384-well source plate layout (Fwd/Rev interleaved) + transfer list. JANUS: Fwd/Rev 96-well rack layout + transfer list. CSV also supported
- **Workspace save/load**: Save parameters + design results as a `.kuro.json` file for cross-session portability
- **Desktop GUI**: Cross-platform app based on Tauri v2 + React 19 (Windows / macOS / Linux)

## Selection Strategies (EVOLVEpro / MULTI-evolve mode)

When loading a scored CSV (EVOLVEpro or MULTI-evolve), KURO applies the configured selection strategy to choose which mutations to design primers for. Strategies are independent checkboxes and can be combined.

| Strategy | Description | When to use |
|----------|-------------|-------------|
| **Top-N by score** | Select the top N mutations ranked by predicted fitness score (y_pred / property_value descending). N = max primers setting (default 95). | Default ranking. Use when predicted fitness is the only criterion. |
| **Position diversity** | Limit the number of mutations per amino acid position (default: 1 per position). When two variants at the same position score within 2%, the more conservative substitution (lower Grantham 1974 distance) is preferred. Applied as a pre-filter before other strategies. | Prevent over-sampling at mutational hot spots. |
| **Domain diversity** | Allocate mutation quota proportionally (by domain length) or equally across protein structural domains. Domains are auto-fetched from InterPro/Pfam via UniProt accession, or entered manually. Under-filled domains show a warning (⚠). | Ensure coverage across all functional regions, especially when one domain dominates the y_pred ranking. |
| **Pareto diversity** | Greedy maximin position selection: iteratively pick the mutation whose position is farthest from all already-selected positions. Maximizes spatial spread across the protein sequence. | Prevent clustering of mutations in a narrow region. Inspired by the MODIFY approach (Ding et al., *Nature Communications*, 2024). |
| **Entropy-guided** (β) | Blends per-position Shannon entropy of the y_pred distribution (weight 0.3) into the Pareto score. Positions where many mutations score similarly (high uncertainty) are prioritised. | Escape local optima. Useful when EVOLVEpro predictions converge on a narrow region but the landscape may have multiple peaks. Requires Pareto diversity to be enabled. |

**Combination examples:**
- Domain + Pareto: Allocate quota per domain, then apply Pareto spread within each domain
- Position + Domain: Cap per-position count, then distribute across domains
- Pareto + Entropy-guided: Spatial spread with uncertainty-driven exploration

**Reference:**
- Ding D, Shaw AY, Sinai S, et al. Protein design using structure-predicted residue preferences and sequence-predicted fitness. *Nature Communications*, 15:6729 (2024). PMID:39080249 — MODIFY: Pareto fitness-diversity co-optimization

## Installation

Download the latest installer from [Releases](https://github.com/gyuminlee-repo/KURO/releases).

- **Windows**: `KURO_x.x.x_x64-setup.exe` (NSIS installer)

## Usage

1. Click **Try sample →** (top of Input panel) to load example files and see a result immediately, or:
2. Load a sequence file (GenBank .gb / SnapGene .dna)
3. Verify the target gene CDS in the Target Gene dropdown (auto-selected)
4. Enter mutations (direct text input, EVOLVEpro CSV, or MULTI-evolve CSV)
5. Select a codon strategy (Min. changes / Optimal)
6. (Optional) Adjust Tm targets, GC% range, primer length in Advanced Options
7. Click **Design Primers**
8. Click a Fwd/Rev sequence → swap primers in the candidate comparison popover
9. Click the HP column → hairpin/homodimer details (Tm, dG)
10. File → Export Excel / Save Workspace

For detailed instructions, see the [User Guide](USER-GUIDE.md).

## License

[GPL v2](LICENSE)
