# Parameter Panel

![Advanced options expanded](../screenshots/06-parameter-advanced.png)

The Parameter panel controls the polymerase profile and the primer Tm/GC/length constraints. The codon table is not set here, it follows the **Organism** chosen beside the target gene on the sequence input panel.

## Polymerase

Seven bundled profiles (Taq, Phusion, Q5, KOD, DreamTaq, TAKARA_GXL, Q5 SDM). Selecting a profile loads its recommended annealing-temperature rule, GC range, and overlap mode; the design-time Tm targets remain independently adjustable.

Custom profiles — see [Custom Polymerase Editor](custom-polymerase-editor.md).

## Codon selection

There is no strategy control. The select that stood here was removed in v0.16.60, because both of its values produced the same candidate pool and differed only in list order, which the engine re-sorted by penalty anyway.

Every synonymous codon for the target amino acid now competes. The wild-type codon is dropped, so are the codons the selected organism uses for less than 10% of that amino acid, and the design penalty prices each survivor on base changes from the wild-type codon (0 / 2 / 4 for 1 / 2 / 3 changes) and on host usage (4.0 x (1 - usage fraction)) alongside Tm and GC. The one codon-related user input is therefore the organism.

Five codon tables ship, and further organisms are installed per user, see [Configuration](configuration.md).

## Mutations count

Target number of successful designs. Default 95 (one plate minus controls). The organism defaults to *E. coli* and is switched in the **Organism** dropdown on the sequence input panel.

Cap: 10,000 (v1.33.6+).

Below the input: plate preview (`Math.ceil(N / 96)`).

## Advanced options

- **Tm targets**: fwd / rev / overlap (°C)
- **GC range**: min / max (%)
- **Primer length range**: fwd-min/max, rev-min/max — overrides polymerase default
- **Fill on failure**: auto-extend pool with buffer candidates when a mutation fails
