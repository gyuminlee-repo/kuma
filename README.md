# KURO — Kernel for Upstream Recombination Oligodesign

[한국어](README.ko.md) | **English**

Desktop app for batch SDM primer design based on Gibson Assembly.

![KURO Overview](docs/kuro_overview.png)

https://github.com/user-attachments/assets/f95e65ca-22d2-4479-a06b-8dcd553571be

Given a mutation list (plain text / EVOLVEpro CSV) and a template sequence (GenBank / SnapGene), KURO automatically designs SDM primer pairs using the overlap extension method.

## Features

- **EVOLVEpro CSV input**: Load EVOLVEpro output CSV → sort by y_pred descending → auto-select the configured number of variants. Optional **position diversity** filter limits mutations per amino acid position. Optional **domain diversity** distributes selections across protein structural domains (auto-fetched from InterPro/Pfam or manual input). Optional **Pareto diversity** maximizes position spread via MODIFY-style fitness-diversity co-optimization
- **Batch mutation parsing**: Mutation list in `Q232A` format → automatic codon position calculation + WT codon validation
- **Codon strategy selection**: Choose between Min. changes (fewest base changes from WT) or Optimal (E. coli-optimized codon)
- **Overlap upstream design**: Overlap region is placed immediately upstream of the mutation codon (EVOLVEpro convention)
- **Tm calculation**: Fixed SantaLucia 1998 (polymerase-independent). Default targets: Fwd 62°C, Rev 58°C, Overlap 42°C. Adjustable in Advanced Options
- **Progressive Tm tolerance**: Starts at ±0.5°C for Fwd/Rev independently, expanding by ±0.5°C per step (up to ±3.0°C)
- **GC% range**: Default 40-60% (adjustable in Advanced Options). Primers outside range receive a penalty
- **Primer length limit**: Optional Fwd/Rev min/max length constraint (adjustable in Advanced Options)
- **Hairpin / Homodimer check**: Secondary structure check via primer3 calc_hairpin/calc_homodimer. Displays Tm and dG (kcal/mol)
- **Column sorting**: All result columns sortable (except sequences). Plate map export respects current sort order
- **Candidate comparison and swap**: Click a primer sequence to open a candidate comparison popover (clickable even with a single candidate). Manually swapped primers are highlighted in amber in the result table
- **Custom primer evaluation**: Enter a sequence directly in the candidate popover → Tm, GC%, hairpin, and off-target are calculated immediately
- **Failed mutation retry**: Click a failed mutation → adjust Tm/GC%/length/tolerance → re-design with modified parameters → select from candidates
- **Fill on failure**: When enabled (default), automatically fills the requested mutation count from extra candidates when some mutations fail
- **Off-target detection**: Automatic detection of non-specific binding on the template sense/antisense strand. Click OT `!!` to view a detailed popover with binding position, strand, and Tm
- **96-well Plate Map**: Linked Fwd/Rev plate. Multi-plate slide for >96 mutations (Plate N Fwd ↔ Plate N Rev). Synchronized with table sort order
- **Workspace save/load**: Save parameters + design results as a `.kuro.json` file for cross-session portability
- **Desktop GUI**: Cross-platform app based on Tauri v2 + React 19 (Windows / macOS / Linux)

## Installation

Download the latest installer from [Releases](https://github.com/gyuminlee-repo/KURO/releases).

- **Windows**: `KURO_x.x.x_x64-setup.exe` (NSIS installer)

## Usage

1. Load a sequence file (GenBank .gb / SnapGene .dna)
2. Verify the target gene CDS in the Target Gene dropdown (auto-selected)
3. Enter mutations (direct text input or load EVOLVEpro CSV)
4. Select a codon strategy (Min. changes / Optimal)
5. (Optional) Adjust Tm targets, GC% range, primer length in Advanced Options
6. Click **Design Primers**
7. Click a Fwd/Rev sequence → swap primers in the candidate comparison popover
8. Click the HP column → hairpin/homodimer details (Tm, dG)
9. File → Export Excel / Save Workspace

For detailed instructions, see the [User Guide](USER-GUIDE.md).

## License

[GPL v2](LICENSE)
