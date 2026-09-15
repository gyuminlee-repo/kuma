# Step 3. Parameters

Specify the polymerase profile, codon strategy, and Tm/GC ranges.

## Polymerase profile

7 built-in + custom:

- Taq, Phusion, Q5, Q5 SDM, KOD, DreamTaq, TAKARA_GXL (default KOD)
- Custom profiles are saved to `~/.kuma/kuro/custom_polymerases.json`.

When a profile is selected, the values that reach the design are the GC range and the overlap mode. Design-time Tm is a fixed SantaLucia 1998 (Benchling) scale, so it does not change when the profile changes. The Tm method · salt · DNA values of a profile are used only to compute the recommended annealing temperature (Ta).

## Codon strategy

| Value | Meaning |
|---|---|
| Min. changes | Fewest base changes from the WT codon |
| Optimal | E. coli optimal codon |

## Tm / GC

- Default: Fwd 62 °C, Rev 58 °C, Overlap 42 °C
- Tolerance: ±0.5 ~ ±10.0 °C (default 3.0)
- GC range: 40-60 % (adjusted in Advanced Options)

## Length

Option to limit Fwd/Rev min/max length.

## Changes in v0.9.2.x

- All local state of the ParameterPanel is flushed to the store when Next is clicked. The values in the Design summary card of the Submit step always match.

→ [Step 4. Submit Design](kuro-04-submit.md)
