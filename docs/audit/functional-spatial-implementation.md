# Exact-frame spatial selection and functional context

Base: public main `9b9fd8682ba97a225a839d00f21b6ec7cc5b50f4`.
This implementation is separate from PRs #2, #3 and #4. It does not copy their
unmerged product changes or introduce a second production FPS algorithm.

## What the app supports

An explicit session-only option under structural diversity selects single-site
substitutions from the full eligible pool. It reuses `structural_diversity_select`
with zero score blending and no anchors. The configured score direction chooses
the representative substitution at each site and the initial point; score ties
use canonical variant IDs within a site and reference position between sites.
This is an opt-in policy, not a claim that score predicts fitness or that FPS is
the optimal definition of protein-wide diversity.

The bounded source is an AlphaFold accession PDB with one model/chain, standard
residue identities, contiguous author numbering from 1 and no alternate or
insertion identities. A unique exact reference interval is required. Coordinates
are in Angstroms; nonfinite C-alpha points are excluded and reported. Unsupported
files, homolog substitutions/indels, ambiguous placement, mismatched mutation
wild-type identities and insufficient unique sites fail explicitly. Local
PDB/mmCIF/zip input remains available through the existing modes but is not
silently accepted by this new strict path.

The result binds raw source PDB hash, reference hash, candidate-file hash, count,
policy, score direction and explicit reference-to-structure positions. The
viewer consumes the same PDB bytes and mapping. Before design the app revalidates
the candidate set and hashes; a change requires reviewing a new selection.
Cross-variant rescue and hidden count expansion are disabled in this option.
The certificate is not restored as trusted state; workspace/autosave restore
turns the option off and requires a new selection. Existing modes and multisite
import remain available.

Strict-stage exclusions are separate from blank/invalid-score parser omissions,
start-position filtering inherited from the loader, duplicate variant rows and
same-site representative reduction. An absent/all-blank score column is marked
unavailable; a real all-zero column remains a scored input.

## Functional information is explanatory

UniProt active/binding responses now retain source-frame feature locations,
descriptions, evidence and ligand metadata when present. Query failure and an
empty matching-feature result are distinct. The compatible integer arrays remain
for existing callers, but the strict preview does not use them to claim projected
functional labels: source-sequence equivalence and uncertain/ranged locations
have not been independently validated. It shows source records with an explicit
unverified-projection label and suppresses functional overlays on strict points.

Domain-unassigned does not establish a linker, IDR or lack of function. Features
are not automatically functional units. Crystal contacts are not established
biological interfaces. No functional weights, automatic quotas, new prediction
model or annotation-dependent ranking is introduced. Defining a functional
exploration/protection policy remains a separate evidence and user-purpose gate.

## Confirmed corrections

- Legacy exact-substring coordinates are reindexed by the unique terminal
  offset and limited to the reference interval. Repeated placements and missing
  sequence no longer establish a verified frame. Three regressions failed on
  the original source before correction; a C-terminal regression was added too.
- Kappa UI text is aligned with the existing calculation direction. Existing
  numerical behavior is preserved.
- A manually uploaded viewer structure clears overlays from the previous source.

## Algorithm decision

The separately frozen [offline pilot](spatial-method-pilot-20261009/README.md)
compares the current FPS with a bounded swap refinement, random references and
tiny exact oracles. Refinement sometimes improves minimum separation while
worsening coverage and adding computation. Keep FPS in the app; refinement is
offline only. Public structures are geometry surrogates, not actual scored
variant pools or measured efficacy trials. Optional functional masks were not
evaluated by that frozen pilot and are not claimed validated.

## Verification boundaries

Automated Python/RPC and frontend tests exercise source mapping, selection,
certificate invalidation, annotation disclosure and exact design forwarding.
Final commands/counts and exact-head remote CI are recorded in the PR description.
The local sync check uses the same generated NOTICE placeholder as CI; it is not
a release notice bundle. Native Tauri interaction, graphical 3D rendering on
target hardware, live AlphaFold/UniProt app calls and biological effectiveness
are not established by mocked component/RPC tests. No release or merge is made.
The isolated cloud runner has no Cargo executable, no DISPLAY/WAYLAND_DISPLAY,
and no GTK3/WebKitGTK 4.1 pkg-config packages. Native Tauri launch was therefore
not attempted; the user's computer was not used. Remote CI supplies its own
Rust/build environment, but a green compile is not native interaction evidence.

Finite coordinates and exact sequence correspondence do not establish a
representative conformation or reliable interdomain placement. No universal
identity or confidence threshold is proposed. Missing annotation is unknown,
and spatial separation does not prove functional independence or reduced
epistasis.
