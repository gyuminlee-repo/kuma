# Distinct-variant budgets: implementation and verification

This follow-up is based on PR #5 (`2b9218268cce7cba876742fda8a4ff94369ab505`).
Its new application behavior is an explicit budget choice inside strict spatial
selection. The existing unique-site policy remains the default. The new policy
counts distinct variant IDs and preserves different amino-acid substitutions at
the same position. A nullable per-site cap is a declared constraint, not an
automatic diversity or biological threshold.

The confirmed input contract is the complete EVOLVEpro `df_test` unmeasured
prediction pool, from which the user requests N distinct variants. N is variable;
95 is an example, not a fixed limit. Every selected ID must already occur in the
supplied CSV. The importer does not independently authenticate an EVOLVEpro round.
The strict path currently supports single substitutions only; multisite input
fails explicitly and remains available through the existing non-strict workflow.
If M=N eligible variants remain after declared policies, the selected set cannot
change. For M>N, spatial selection may change score Top-N membership. No larger
pool, shortlist or score floor is inferred. Actual user `df_test` files have not
been tested; synthetic compatible CSV checks and the auxiliary ESM2/DMS pilot are
not an EVOLVEpro recommendation-round reproduction.

## What is connected to the app

- Same exact AlphaFold reference correspondence as PR #5. Source, reference,
  candidate input and policy are bound to the reviewed result.
- Existing full-pool FPS, kappa zero and no implicit anchors. At a fixed site,
  substitutions have the same coordinate. Once all eligible coordinates are
  covered, additional variants are score/tie allocation with zero spatial gain.
- N distinct variants, U occupied sites, site multiplicities, duplicate-inclusive
  minimum distance and unique-site minimum distance are separate fields.
- Explicit cap and capacity errors. Identical IDs do not fill multiple slots.
  No new variant is manufactured and no rescue silently replaces the reviewed IDs.
- Policy/cap edits invalidate selection. The viewer retains all selected
  substitutions in its table/hover while highlighting a site once. Design forwards
  exactly the reviewed variant IDs. Workspace restoration disables strict mode.
- Functional information remains explanatory; annotation absence does not mean
  nonfunctional. No functional score, quota or annotation-density reward was added.

## What remains experimental or unverified

`residue_mapping.py` is an offline API with a real mmCIF polymer/observation adapter,
optional homolog alignment, explicit residue-level SIFTS evidence validation and
provenance-bound pLDDT/PAE diagnostics. It is not wired into the application
certificate or viewer. The app does not thereby gain general PDB/homolog support,
automatic SIFTS retrieval, missing-loop coordinates or confidence filtering.
See [its contract](residue-mapping-contract.md) for the executed public-file and
synthetic checks.

The [frozen-scorer pilot](dms-variant-pilot-20261009/README.md) is retrospective
software evaluation. Selection-time scores and measured assay labels are separate.
It does not establish beneficial mutations, functional independence, improved
prospective experimental success or broad protein-family generalization.

### Concrete follow-up gates

Official source checks on 2026-10-09 retrieved UniProt entries
[P42212](https://rest.uniprot.org/uniprotkb/P42212.json) and
[P0CH08](https://rest.uniprot.org/uniprotkb/P0CH08.json), plus model/PAE URLs from
the corresponding [GFP](https://alphafold.ebi.ac.uk/api/prediction/P42212) and
[RL40A](https://alphafold.ebi.ac.uk/api/prediction/P0CH08) AlphaFold APIs. These
sources are available. Their v6 coordinates differ from the frozen ProteinGym
coordinates, so their PAE cannot be attached to the existing pilot frames.
GFP's assay reference also differs from the canonical reference at position 64.
RL40A's 128-residue reference matches, but its tested positions 2–76 occupy the
ubiquitin portion, not several independently validated functional units.

A future confidence-aware comparison can explicitly freeze a new, matching
model/PAE pair and repeat geometry sensitivity checks. It must not silently replace
the frozen pilot. Functional-feature projection additionally needs exact or
explicitly supported sequence correspondence, location qualifiers and evidence;
feature count is not functional diversity or fitness. The input boundary is now specified as the full `df_test` pool and a user-selected
N. Validation against an actual file, including its mutation notation and whether
it contains multisite variants, remains an application evidence gate. General homolog application integration requires the RPC, certificate,
viewer and design consumers to retain the new full residue identities. Those
consumers are not yet validated for the offline mapper's broader inputs.

Native GUI testing remains blocked. A separate cloud feasibility check installed
official Rust/GTK/WebKit/Xvfb tools in isolation, but the sandbox denied creation of
AF_UNIX sockets (`EPERM`) and Xvfb could not start its display. TCP loopback worked;
this was not a claim that all networking failed. App native build, launch,
screenshots and GUI flows were not executed. The separate desktop task did not
execute because its task quota was unavailable. Component/RPC tests cannot close
that gate. The task-specific native tools were removed after the failed feasibility
check.

## Original budget implementation validation record

- PR #5 starting point: 22 strict/frame focused tests passed in this new checkout.
- Three new budget regressions first failed on the starting implementation: 95
  variants across five sites, explicit cap semantics and transformed/reordered
  inputs. They passed after the implementation.
- Expanded strict/frame/budget tests: 35 passed. Earlier strict/loader/legacy
  regression run: 81 passed; these overlapping runs are not summed.
- Independent review compared the existing unique-site result with the old
  implementation on 100 randomized pools/counts/tied and negative scores, with
  identical ordered selections. This is tested equivalence, not a universal proof.
- Full Python run: 5,695 passed / 115 skipped / 18 subtests, exit 0, 727.43 s.
  Its collection preceded one extra candidate-boundary regression; the final
  budget module's 14 tests were separately rerun and passed after that addition.
- Full frontend run: 237 files / 2,430 tests passed, exit 0. Subsequent locale-only
  clarification passed focused UI tests and all ten locale parity/lint checks.
- Final Python typecheck: zero errors, nine optional-import warnings. TypeScript,
  cross-layer sync and frontend build passed; Vite reported its existing large-
  chunk warning. Sync used CI's generated NOTICE placeholder, not release notices.
- Independent bounded validation: 166 focused Python/legacy tests, 170 frontend
  tests, TypeScript check, the 100-case old-policy comparison, public mmCIF
  comparison and full DMS replay with label-reversal/removal controls. The final
  purpose clarification and 14 budget tests were separately reviewed again.
- Exact-head remote results are recorded in the PR after completion. No native
  GUI or actual EVOLVEpro recommendation round is certified by these test counts.

한국어 요약: 실제 앱에는 서로 다른 변이 수와 위치 수를 구분하는 명시적 예산
정책을 연결했다. 같은 위치의 다른 치환을 보존하고 구조상 같은 점에 있는 추가
변이를 공간 분산 향상으로 계산하지 않는다. 새 잔기 대응·신뢰도 도구는 오프라인
검증 단계이며 homolog 앱 지원이나 기능 최적화 완성으로 소개하지 않는다.
네이티브 화면은 실행 제약으로 검증하지 못했고 자동화 검사와 구분한다.

## Full df_test comparison follow-up

The preview compares the spatial result with configured-score Top-N on exactly the
same eligible pool after the budget and cap policy. Unique-site mode first retains
one representative per site; distinct-variant mode retains substitutions subject
to the explicit cap. Missing-coordinate or parser-rejected rows are not silently
included only in the baseline. Existing exclusion counts remain separately visible.

Both results report variant count, occupied-site count, maximum site multiplicity,
minimum distance between occupied sites and mean/max candidate-to-selected distance
in angstroms. Coverage targets are the eligible unique sites with equal weight per
site, including selected sites at zero distance; this is not whole-protein coverage.
A single occupied site has no pair-distance statistic. Integer counts are exact.

With available scores, the preview also reports raw mean score, average tied rank,
Top-N overlap and `score_gap_to_top_n`: the direction-aware difference in **mean**
raw score. Positive means a worse average under the configured asc/desc ordering,
not fitness loss. Tied ranks are averaged within the same effective pool. An
absent score source yields no score baseline or invented rank. Real zero scores
remain valid scores. Nonfinite diagnostic arithmetic yields an unavailable value
without changing selection or emitting invalid JSON.

Follow-up regression cases include variable N=1/12/95/100, M=N and M<N,
normalised aliases and final-sequence uniqueness, no-op exclusion, malformed/WT/
multisite rejection, partial missing scores, ascending/descending directions,
explicit caps and the unique-site representative policy. A hand-calculated example
checks every displayed comparison independently of the selection implementation.
Current run results and exact-head CI are recorded in the pull request after they
complete; these checks do not certify native UI execution or actual EVOLVEpro data.

한국어 추가 요약: 입력은 EVOLVEpro 전체 df_test 예측 후보이며 사용자가 정한 N개의
서로 다른 변이를 고른다. 같은 예산·위치 상한을 적용한 유효후보의 점수 상위 N개와
공간 선정 결과를 비교한다. 점수 방향에 따른 평균 차이와 위치 집중·3D coverage를
함께 표시하며 점수를 실제 기능이나 fitness로 해석하지 않는다. 현재 strict 경로는
단일 치환만 지원하고 실제 사용자 df_test 및 네이티브 화면 검증은 남아 있다.
