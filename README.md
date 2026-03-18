# KURO — Kernel for Upstream Recombination Oligodesign

[한국어](README.ko.md) | **English**

Desktop app for batch SDM primer design based on Gibson Assembly.

Given a mutation list (plain text / EVOLVEpro CSV) and a template sequence (GenBank / SnapGene), KURO automatically designs SDM primer pairs using the overlap extension method.

## Features

- **EVOLVEpro CSV input**: Load EVOLVEpro output CSV → sort by y_pred descending → auto-select the configured number of variants
- **Batch mutation parsing**: Mutation list in `Q232A` format → automatic codon position calculation + WT codon validation
- **Codon strategy selection**: Choose between Min. changes (fewest base changes from WT) or Optimal (E. coli-optimized codon)
- **Overlap upstream design**: Overlap region is placed immediately upstream of the mutation codon (EVOLVEpro convention)
- **Tm calculation**: Fixed SantaLucia 1998 (polymerase-independent). Default targets: Fwd 62°C, Rev 58°C, Overlap 42°C. Adjustable in Advanced Options
- **Progressive Tm tolerance**: Starts at ±0.5°C for Fwd/Rev independently, expanding by ±0.5°C per step (up to ±3.0°C)
- **GC% range**: Default 40-60% (adjustable in Advanced Options). Primers outside range receive a penalty
- **Hairpin / Homodimer check**: Secondary structure check via primer3 calc_hairpin/calc_homodimer. Displays Tm and dG (kcal/mol)
- **Candidate comparison and swap**: Click a primer sequence to open a candidate comparison popover (clickable even with a single candidate). Manually swapped primers are highlighted in amber in the result table
- **Custom primer evaluation**: Enter a sequence directly in the candidate popover → Tm, GC%, hairpin, and off-target are calculated immediately
- **Off-target detection**: Automatic detection of non-specific binding on the template sense/antisense strand. Click OT `!!` to view a detailed popover with binding position, strand, and Tm
- **96-well Plate Map**: Linked Fwd/Rev plate. Multi-plate slide for >96 mutations (Plate N Fwd ↔ Plate N Rev). Synchronized with table sort order
- **Workspace save/load**: Save parameters + design results as a `.kuro.json` file for cross-session portability
- **Desktop GUI**: Cross-platform app based on Tauri v2 + React 19 (Windows / macOS / Linux)

## Architecture

```
┌──────────────────────────────────────────┐
│  React 19 + Tailwind + shadcn/ui        │
│  Zustand 5 (state) + TanStack Table     │
├──────────────────────────────────────────┤
│  Tauri v2 Shell Plugin (JSON-RPC 2.0)   │
├──────────────────────────────────────────┤
│  Python Sidecar (PyInstaller)           │
│  kuro package (primer3-py)      │
└──────────────────────────────────────────┘
```

## Installation and Development

### Prerequisites

- Node.js 18+
- Rust (Tauri v2)
- Python 3.11+ + pip

### Frontend

```bash
npm install
npm run dev          # Vite dev server (port 1421)
```

### Python Backend

```bash
pip install primer3-py==2.3.0 biopython==1.84 openpyxl==3.1.5
```

### Build

```bash
# Generate sidecar binary
npm run sidecar:build

# Build Tauri app (with sidecar)
npm run build:all
```

## Usage

### GUI

1. Load a sequence file (GenBank .gb / SnapGene .dna)
2. Verify the target gene CDS in the Target Gene dropdown (auto-selected)
3. Enter mutations (direct text input or load EVOLVEpro CSV)
4. Select a codon strategy (Min. changes / Optimal)
5. (Optional) Adjust Tm targets and GC% range in Advanced Options
6. Click Design Primers
7. Click a Fwd/Rev sequence → swap primers in the candidate comparison popover
8. Click the HP column → hairpin/homodimer details (Tm, dG)
9. File → Export TSV / Export Excel / Save Workspace

For detailed usage instructions, see the [User Guide](USER-GUIDE.md).

### Multi-plate Design

The default Mutations value is **95**, optimized for a single 96-well plate.
To design more variants at once, adjust both the input file and the Mutations value.

**Procedure**

1. Prepare an EVOLVEpro output CSV containing the desired number of variants (200, 300, etc.).
2. In the KURO parameter panel, change the **Mutations** number to match that count.
   - 1 plate: 95 / 2 plates: 192 / 3 plates: 288
3. Load the CSV and run Design Primers.
4. In the Plate Map tab, use the `‹ Plate 1/N ›` slider to navigate between plates. The Rev plate for each number contains only the reverse primers corresponding to the mutations in the matching Fwd plate.

> If the Mutations value is smaller than the number of variants in the CSV, only the top N by y_pred are selected. It is recommended to match the Mutations value to the number of variants in the CSV.

### CLI

```bash
python -m kuro design \
  --fasta <your_sequence.gb> \
  --target-start <cds_start> \
  --mutations <mutations.csv> \
  --polymerase "Benchling" \
  --overlap 20 \
  --output results/

python -m kuro plate-map \
  --primers results/sdm_primers.tsv \
  --output results/plate_mapping.xlsx
```

## Project Structure

```
KURO/
├── src/                          React frontend
│   ├── store/appStore.ts         Zustand state + RPC actions
│   ├── lib/ipc.ts                JSON-RPC communication layer
│   ├── hooks/useSidecar.ts       Sidecar lifecycle hook
│   ├── types/models.ts           TypeScript interfaces
│   └── components/
│       ├── layout/AppLayout.tsx  2-column layout + menu bar
│       ├── panels/               Input + parameter panels
│       └── widgets/              ResultTable (aa sort, candidate comparison popover, position group badge) + PlateMap
├── src-tauri/                    Tauri v2 desktop shell
├── python-core/                  Sidecar wrapper
│   ├── sidecar_main.py           JSON-RPC dispatcher (12 methods)
│   └── build_sidecar.py          PyInstaller build script
├── kuro/                 Python backend
│   ├── sdm_engine.py             SDM design engine (upstream overlap + full Tm + off-target + hairpin/homodimer)
│   ├── mutation.py               Mutation parsing + codon substitution
│   ├── overlap.py                Overlap window (upstream only) + reverse complement
│   ├── plate_mapper.py           Primer list mapping
│   ├── polymerase.py             Polymerase profiles (built-in)
│   └── resources/                polymerase_profiles.json
├── tests/                        pytest (38 tests)
├── fixtures/                     Test data
└── .github/workflows/build.yml  Cross-platform CI
```

## JSON-RPC Methods (Sidecar)

| Method | Input | Output |
|--------|-------|--------|
| `list_polymerases` | — | `[{name, manufacturer, fidelity}]` |
| `load_fasta` | `filepath` | `{header, seq_length, genes[{gene, product, cds_start, cds_end, aa_length}]}` |
| `parse_mutations_text` | `text` | `[{raw, wt_aa, position, mt_aa}]` |
| `design_sdm_primers` | `{fasta_path, target_start, ...}` | `{results[], success_count, total_count, failed_mutations[]}` |
| `get_alternatives` | `{mutation}` | `{mutation, candidates[]}` |
| `swap_primer` | `{mutation, candidate_idx}` | Swapped `SdmPrimerResult` |
| `get_plate_map` | — | `{mappings[], dedup_info}` |
| `export_tsv` | `filepath` | `{success, filepath}` |
| `export_excel` | `filepath` | `{success, filepath}` |
| `evaluate_primer` | `{mutation, fasta_path, forward_seq, reverse_seq}` | Custom primer evaluation `SdmPrimerResult` |
| `save_workspace` | `{filepath, data}` | `{success, filepath}` |
| `load_workspace` | `{filepath}` | workspace JSON object |

## Tests

```bash
python -m pytest tests/ -v
# 38 passed
```

## Dependencies

### Python

| Package | Version | Purpose |
|---------|---------|---------|
| primer3-py | 2.3.0 | Tm calculation (SantaLucia/Owczarzy) |
| biopython | 1.84 | Sequence processing |
| openpyxl | 3.1.5 | Excel output |

### Frontend

| Package | Purpose |
|---------|---------|
| React 19 | UI framework |
| Zustand 5 | State management |
| TanStack React Table | Primer table |
| Tauri v2 | Desktop shell |
| Tailwind CSS 3 | Styling |
| shadcn/ui | UI components |
