# KURO User Guide

[한국어](USER-GUIDE.ko.md) | **English**

Desktop app for batch Site-Directed Mutagenesis (SDM) primer design.
Given a mutation list (plain text / EVOLVEpro CSV) and a template sequence (GenBank / SnapGene), KURO automatically designs SDM primer pairs using the overlap extension method.

---

## 1. Quick Start

1. When the app starts, the sidecar (Python backend) connects automatically. Wait until "Ready" appears in the status bar.
2. Click the **Browse** button to load a sequence file (GenBank .gb / SnapGene .dna).
3. The CDS start ATG is auto-selected (based on the longest ORF). Change it from the dropdown if needed.
4. Enter a mutation list as text or load an EVOLVEpro CSV.
5. Select a codon strategy: Min. changes (fewest changes from WT) or Optimal (E. coli-optimized codon).
6. Set the Mutations count (default 95; multi-plate is auto-generated when count exceeds 96).
7. Select a polymerase profile in the Parameters panel. KURO loads that profile's Tm targets and GC range automatically.
8. (Optional) Click **Custom Polymerase** to create or edit a user-defined profile. Saved profiles persist across app restarts.
9. (Optional) Adjust Tm targets and GC% range in Advanced Options.
10. Click **Design Primers**.
11. The primer table is generated. Click the Mutation column header to sort by amino acid position.
12. Click a Fwd/Rev sequence to open the candidate comparison popover. Click the HP column to view hairpin/homodimer details.
13. From the File menu, use Export Excel / Save Workspace to export or save the session.

![Initial screen](docs/screenshots/01-initial.png)

---

## 2. Preparing the FASTA File

### Format Requirements

- Single-record FASTA (must contain exactly one record)
- Uppercase sequence recommended (lowercase is auto-converted internally)
- Must include the full plasmid sequence (do not extract the CDS separately)

```
>pSHCE-dmpR_20160502  (4532 bp)
AAATTCCGGATGAGCATTCATCAGGCGGGCAAGAATGTGAATAAAGGCCGG...
```

### Finding the CDS Start Position

KURO accepts the CDS start codon (ATG) position as a 0-based index.

**In SnapGene:**
1. Click the target gene CDS feature on the plasmid map
2. Note the start position in the feature information
3. SnapGene uses 1-based indexing, so subtract 1 from the displayed value

**In Benchling:**
1. Select the target CDS annotation in the Sequence Map
2. Note the start position and subtract 1 (Benchling is also 1-based)

**In a text editor:**
1. Find the target ATG in the FASTA sequence
2. Count from the first base (0-indexed) to calculate the ATG position

When a FASTA is loaded, KURO automatically scans all ATG positions in the sequence, calculates the downstream ORF length for each ATG, and auto-selects the one with the longest ORF.

---

## 3. Entering Mutations

### Text Input

Enter one mutation per line. Format: `{WT amino acid}{position}{MT amino acid}`

```
Q232A
Y233A
E335A
E167A
K200A
```

- Amino acids in single-letter uppercase code
- Position is 1-based (first methionine of CDS = 1)
- Blank lines are ignored

### EVOLVEpro CSV Input

Select EVOLVEpro mode and use the Browse button to load an EVOLVEpro output CSV.

- CSV must contain `variant` and `y_pred` columns
- Variants are sorted by y_pred descending; the number specified in the Mutations setting is auto-selected (default 95)
- **Position diversity** (optional): Enable the checkbox to limit mutations per amino acid position. When high-scoring mutations cluster at the same position (e.g., Q10A, Q10L, Q10V), only the top N per position are kept, diversifying the search space
- **Domain diversity** (optional): Distributes variant selection across different protein structural domains. Enter a UniProt accession ID and click Fetch to auto-retrieve domain boundaries from InterPro/Pfam. Choose between Proportional (quota by domain length) and Equal (same quota per domain) strategies. Domains can also be added or removed manually for offline use
- **Pareto diversity** (optional): MODIFY-style fitness-diversity co-optimization. Maximizes position spread among selected variants using a greedy maximin algorithm. Can be used alone or combined with domain diversity (applies Pareto selection within each domain). All three diversity options are independent toggles

#### Selection Strategy Decision Guide

| Strategy | When to use |
|----------|-------------|
| **Top-N only** | Default. Use when y_pred alone is sufficient for ranking |
| **Position diversity** | When multiple mutations cluster at the same position (hot spot). Limits per-position count to broaden the search space |
| **Domain diversity** | When one domain monopolizes the top y_pred ranks. Ensures balanced exploration across functional regions |
| **Pareto diversity** | When maximizing physical position spread. Prevents clustering via greedy maximin selection |
| **Position + Domain** | Combines per-position limits with cross-domain balancing. Useful when hot spots exist within a dominant domain |
| **Domain + Pareto** | Applies Pareto spread within each domain. Maximizes both functional and positional diversity |
| **Pareto + Entropy-guided** | Blends Pareto spread with per-position y_pred entropy (weight 0.3). Prioritises positions where many mutations score similarly (high uncertainty), helping escape local optima in the fitness landscape (marked β) |
- After loading, the text area can be edited directly

![Mutation list input](docs/screenshots/03-mutations-entered.png)

---

## 4. Parameter Settings

### Target Gene

When a sequence is loaded, CDS genes are auto-detected and shown in a dropdown.

- GenBank file: gene name and position are auto-extracted from CDS features. Format: `[gene name] start-end (aa)`
- FASTA file: the longest ORF is auto-detected. Format: `(ORF1) start-end (aa)`
- The longest gene is auto-selected
- Selecting the wrong gene will cause an error during WT amino acid validation

### Codon

Determines the mutation codon selection strategy.

| Strategy | Description |
|----------|-------------|
| **Min. changes** (default) | Prefers the codon with the fewest base changes from the WT codon. Fewer mutation positions in the primer improve synthesis accuracy. Conservative choice when minimizing primer complexity |
| **Optimal** | Prefers the codon with the highest codon usage frequency for the selected organism. Suitable for expression optimization |

**Organism selection**: Choose the host organism from the Organism dropdown in the Input panel. The Optimal strategy uses that organism codon table.

| Organism | Notes |
|----------|-------|
| E. coli K-12 | Built-in codon table (most validated) |
| B. subtilis 168 | Gram-positive. Codon preference differs from E. coli |
| S. cerevisiae | Yeast. Eukaryotic codon optimisation |
| H. sapiens | Human. Suitable for mammalian expression systems |

> **Limitation**: Optimal uses the selected Organism table only. For organisms not in the list, Min. changes is the safer choice.

Both strategies also try alternative codons as candidates and select the primer pair with the lowest penalty.

### Mutations

Sets the **target number of successful designs** (default 95). When "Fill on failure" is enabled, KURO sends extra mutations to the backend and fills the count from next-ranked candidates if some fail. When disabled, exactly N mutations are attempted and failures reduce the final count. When count exceeds 96, the Plate Map is automatically split into multiple plates, and the ‹ › buttons navigate between plates. The Rev plate for each number contains only the reverse primers corresponding to the mutations in the matching Fwd plate.

### Polymerase

Choose the polymerase profile in the Parameters panel before design.

| Option | Description |
|--------|-------------|
| Built-in profile | Loads default Tm targets and GC range for that polymerase |
| Custom Polymerase | Opens a dialog to create or edit a user-defined profile |

Custom profiles are saved to `~/.kuro/custom_polymerases.json` and are reloaded automatically the next time KURO starts.

### Advanced Options

Click the "Advanced options..." link to expand the collapsible panel. If not set, default values are used.

| Parameter | Default | Description |
|-----------|---------|-------------|
| Tm Fwd | 62°C | Target Tm for the full forward primer |
| Tm Rev | 58°C | Target Tm for the full reverse primer |
| Tm Overlap | 42°C | Target Tm for the overlap region |
| GC% | 40-60% | Allowed GC content range. Primers outside range receive a penalty |
| Primer length limit | Off | Enable to set Fwd/Rev min/max primer length (bp). Default when enabled: Fwd 22-45, Rev 22-35 (KOD One: 22–35 bp, Tm >63°C) |
| Fill on failure | On | When some mutations fail, automatically replace with next-ranked candidates to fill the requested count |

Tm calculation uses the SantaLucia 1998 model with fixed conditions (mv_conc=50 mM, dna_conc=250 nM), independent of polymerase type. Because the same primer sequence is ordered regardless of which polymerase is used, the Tm calculation method does not need to change per polymerase.

---

## 5. Interpreting the Primer Table and Tm Conditions

### Column Descriptions

| Column | Description |
|--------|-------------|
| # | Input order (based on EVOLVEpro y_pred descending) |
| Mutation | Mutation notation (e.g., Q232A). Click header to sort by aa position |

All columns except Forward/Reverse Primer are sortable by clicking the column header. The current sort order is reflected in Excel plate map export.
| Forward Primer | Full forward primer sequence. Click to open candidate comparison popover |
| Reverse Primer | Full reverse primer sequence. Click to open candidate comparison popover |
| Fwd / Rev | Primer length (bp) |
| Tm F / Tm R | Full primer Tm |
| Tm Ov | Overlap region Tm |
| Tol | Applied Tm tolerance (shown as ±value for Fwd/Rev separately) |
| Pen | Penalty score (sum of Tm deviation + GC% deviation + codon change count + hairpin/homodimer) |
| Cand | Number of primer candidates for the mutation. Click to sort |
| OT | Off-target detection status. Click `!!` to view a detailed popover with binding position, strand, and Tm |
| HP | Hairpin/Homodimer worst Tm. Click to view details (Tm, dG kcal/mol) |
| GC% F / GC% R | Full primer GC content (40-60% range recommended) |
| WT / MT | Wild-type / mutant codon. MT tooltip changes based on the selected codon strategy |

### Tm Dual Condition

In SDM overlap extension PCR, primer-template annealing must be stronger than primer-primer annealing.

```
Condition: Tm_no_fwd > Tm_overlap + 5  AND  Tm_no_rev > Tm_overlap + 5
```

- **OK (green)**: Both non-overlap Tm values are at least 5°C higher than the overlap Tm. Likely to work under standard PCR conditions.
- **FAIL (red)**: Condition not met. Risk of primer dimer formation in the overlap region.

### GC Content

- Recommended range: 40-60%
- Primers below 40% or above 60% receive a penalty
- Primers below 35% or above 65% trigger a warning message

### Warning Messages

| Warning | Meaning |
|---------|---------|
| `Forward primer too long: N bp` | Primer length exceeds 60 bp. Increased synthesis cost and potential quality issues |
| `Reverse primer too long: N bp` | Same |
| `Fwd GC% out of range: N%` | Forward primer GC% is below 35% or above 65% |
| `Rev GC% out of range: N%` | Reverse primer GC% is below 35% or above 65% |
| `Tm condition not met` | Tm dual condition not satisfied. Consider adjusting Tm targets |
| `Fwd hairpin Tm=X°C (dG=Y kcal/mol)` | Forward primer hairpin Tm exceeds 40°C |
| `Fwd homodimer Tm=X°C (dG=Y kcal/mol)` | Forward primer homodimer Tm exceeds 40°C |

![Design complete — result table](docs/screenshots/04-design-complete.png)

---

## 6. Candidate Comparison

Clicking a Forward or Reverse sequence opens the candidate comparison popover. Even with a single candidate, clicking it allows custom primer input.

### Comparison Items

Candidates are sorted by penalty ascending. #1 is the automatically selected default (best), shown with a green background.

For each candidate, the following values can be compared:
- Forward / Reverse sequence and length
- Tm (Fwd, Rev, Overlap)
- GC% (Fwd, Rev)
- Tolerance (Fwd/Rev), Penalty, Off-target

Hovering over a Penalty cell shows a tooltip with detailed warning items (hairpin, homodimer, GC, etc.).

### Manual Swap

Three buttons are shown for each candidate:
- **Both**: Replace both Forward and Reverse
- **F**: Replace Forward only (Reverse remains unchanged)
- **R**: Replace Reverse only (Forward remains unchanged)

**Reverse propagation**: Changing the Reverse primer automatically propagates to all mutations at the same amino acid position. Mutations at the same position share the same overlap region and therefore must use the same reverse primer.

Manually swapped primers are shown with an **amber background highlight** in the result table to distinguish them from auto-selected primers.

### Custom Primer Input

At the bottom of the popover, enter the Forward sequence in three parts:
- **Overlap** (blue input): 5' end overlap region
- **Codon** (red input): Mutation codon (3 bp)
- **Downstream** (black input): 3' end downstream region

Reverse is entered as a single input. Click **Evaluate** to calculate Tm, GC%, hairpin/homodimer, and off-target. The result is added as a purple-background "custom" row. Custom candidates persist after closing the popover. Apply with the **Use** button or delete with the **×** button.

### Failed Mutation Retry

Click a failed mutation tag in the Failed section below the result table. A popup opens with two recovery options:

**Retry with parameters**: Adjust Tm targets, GC% range, primer length limits, and tolerance max, then click **Retry**. The engine redesigns only this mutation with the adjusted parameters and shows up to 10 candidates sorted by penalty. Click **Select** on the desired candidate to add it to the result table.

**Manual input**: Expand "Or enter manually..." to directly input Forward (Overlap + Codon + Downstream) and Reverse sequences. Click **Evaluate** to calculate metrics and add to results.

---

## 7. Export

### Excel (.xlsx)

File menu > Export Excel

Four sheets are generated per plate. For more than 96 mutations, plates are split (Fwd List 1, Fwd Plate 1, Rev List 1, Rev Plate 1, ...). The Rev plate for each number contains only the reverse primers corresponding to the mutations in the matching Fwd plate (Fwd-Rev pairing).

Sheet structure per plate:
1. **Fwd List** sheet: Forward primer list (Well, Primer Name, Sequence, Length, Tm, Tm_Overlap, WT_Codon, MT_Codon, Mutation). Green background.
2. **Fwd Plate** sheet: Forward 96-well plate layout (`mutation_F` format). Green background.
3. **Rev List** sheet: Reverse primer list (deduplicated, `_R` suffix, same columns as Fwd List). Orange background. Primers shared across multiple mutations have a blue background.
4. **Rev Plate** sheet: Reverse 96-well plate layout (`mutation_R` format). Shared primers in blue background.

Colors match the program UI:
- Green: Forward primers
- Orange: Reverse primers (unique)
- Blue: Reverse primers (shared across multiple mutations)

The Fwd List / Rev List sheets can be submitted directly to an oligo synthesis vendor.

### Workspace (.kuro.json)

File menu > Save Workspace

Saves the current session state as a `.kuro.json` file. Saved items:
- Sequence file path, selected gene
- Mutation list, input mode, parameters (codon strategy, polymerase, mutation count)
- Design output (primer table, failed list, plate map, sort state)

File menu > Load Workspace restores the saved session and displays the previous screen as-is.

![Plate Map — 96-well layout](docs/screenshots/05-plate-map.png)

### Clear All

Click the **Clear All** button at the bottom of the sidebar to reset all inputs and design output.

---

## 8. Troubleshooting

### "expected WT amino acid X at position N, but codon YYY encodes Z"

The CDS Start position is incorrect, causing a codon frame shift. Verify that the selected gene in the Target Gene dropdown matches the intended CDS. Re-check the CDS annotation position in SnapGene/Benchling (1-based → 0-based conversion required).

### Tm condition not met (many FAILs)

Overlap region Tm is too high to maintain a 5°C margin from the non-overlap Tm.

1. **Adjust Tm targets**: Increase Tm Fwd/Rev targets in Advanced Options to widen the gap from overlap Tm.
2. **Use candidate comparison**: Click a Fwd/Rev sequence → select an alternative with a better Tm condition, or enter a custom primer.
3. **Retry failed mutations**: Click a failed mutation tag → adjust parameters → Retry with relaxed constraints.

### "Sidecar not running"

The Python backend (sidecar) failed to start or lost connection.

1. Close and relaunch the app. The sidecar starts automatically on launch.
2. If the error persists, check that the sidecar binary exists in the installation directory and is not blocked by antivirus software.
3. On macOS, confirm the binary is not quarantined: `xattr -d com.apple.quarantine <sidecar-path>`.

### "CSV file missing required 'mutation' column"

The first row of the CSV must include a column named exactly `mutation` (case-sensitive).

### "No valid primer pair found within Tm tolerance"

No primer candidate satisfied the Tm constraints at the default tolerance level.

1. **Increase Tm tolerance**: Open the failed mutation retry popup and raise the tolerance max value (e.g., from ±2 to ±4).
2. **Adjust overlap length**: Shorter or longer overlap regions shift the overlap Tm. Try changing the Tm Overlap target in Advanced Options.
3. **Relax GC% range**: If GC content is also constraining the search, widen the GC% range (e.g., 35-65%).
4. **Use custom primer input**: Enter a manually designed primer via the candidate comparison popover and click Evaluate.
