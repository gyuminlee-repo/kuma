# Parameter Panel

![Advanced options expanded](../screenshots/06-parameter-advanced.png)

The Parameter panel controls the design method, polymerase profile, codon strategy, and primer Tm/GC/length constraints.

## Design method

Choose the cloning chemistry per run:

- **Overlap-extension** (default) — overlap-extension SDM; output is unchanged.
- **Golden Gate (Type IIS)** — designs primers that insert the enzyme recognition site plus a ligation-fidelity-scored fusion overhang around each mutated codon.

When Golden Gate is selected:

- **Enzyme** — six built-in enzymes (BsaI, BsmBI, BbsI, SapI, PaqCI, BspMI). BsaI and BsmBI use on-target ligation-fidelity tables (Potapov 2018) to pick the best overhang; the rest fall back to a functional unscored overhang. Pick **Custom enzyme…** to add your own, saved to `~/.kuma/kuro/custom_enzymes.json`.
- **Codon usage** — organism-aware (Kazusa); a codon that would create a forbidden Type IIS site inside the design window is skipped.
- **Junction** — override the prefix (spacer + recognition site + spacer) and forbidden overhangs (default `AATG`, `AGGT`) for your vector. A prefix that omits the recognition site or mis-positions the cut raises a per-result warning.
- **Tm** — shares the SantaLucia 1998 (SnapGene) model with overlap-extension; the PCR Tm/GC/length parameters below do not apply to Golden Gate.

## Polymerase

Seven bundled profiles (Q5, KOD, Phusion, Herculase II, PfuUltra II, KAPA HiFi, Takara PrimeSTAR GXL). Selecting a profile auto-loads its Tm targets, salt/Mg²⁺ correction, and GC range.

Custom profiles — see [Custom Polymerase Editor](custom-polymerase-editor.md).

## Codon strategy

- **Min. changes** (default): fewest nucleotide changes from WT codon
- **Optimal**: highest-frequency codon for the selected organism

## Mutations count

Target number of successful designs. Default 95 (one plate minus controls). Default organism: *E. coli* — switchable via menu.

Cap: 10,000 (v1.33.6+).

Below the input: plate preview (`Math.ceil(N / 96)`).

## Advanced options

- **Tm targets**: fwd / rev / overlap (°C)
- **GC range**: min / max (%)
- **Primer length range**: fwd-min/max, rev-min/max — overrides polymerase default
- **Fill on failure**: auto-extend pool with buffer candidates when a mutation fails
