# Parameter Panel

![Advanced options expanded](../screenshots/06-parameter-advanced.png)

The Parameter panel controls polymerase profile, codon strategy, and primer Tm/GC/length constraints.

## Polymerase

Seven bundled profiles (Taq, Phusion, Q5, KOD, DreamTaq, TAKARA_GXL, Q5 SDM). Selecting a profile loads its recommended annealing-temperature rule, GC range, and overlap mode; the design-time Tm targets remain independently adjustable.

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
