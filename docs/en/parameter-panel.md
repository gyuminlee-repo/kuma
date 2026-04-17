# Parameter Panel

![Advanced options expanded](../screenshots/06-parameter-advanced.png)

The Parameter panel controls polymerase profile, codon strategy, and primer Tm/GC/length constraints.

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

*Stub — expanded-panel screenshot coming.*
