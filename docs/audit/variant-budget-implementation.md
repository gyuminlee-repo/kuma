# Distinct-variant budgets: implementation and verification

This follow-up is based on PR #5 (`2b9218268cce7cba876742fda8a4ff94369ab505`).
Its new application behavior is an explicit budget choice inside strict spatial
selection. The existing unique-site policy remains the default. The new policy
counts distinct variant IDs and preserves different amino-acid substitutions at
the same position. A nullable per-site cap is a declared constraint, not an
automatic diversity or biological threshold.

The intended use is a diversity-aware subset of supplied EVOLVEpro candidates,
not replacement of EVOLVEpro's predictor. The importer currently treats the whole
input file as its declared candidate pool. It does not infer whether that file is
a final recommendation list or a larger scored test universe. Every selected ID
must already occur in that input. If it contains exactly N eligible distinct
variants and N are requested, the same variant/site multiset must be retained;
selection cannot improve its positional distribution. Reselecting from M>N may
change Top-N membership and model-score rank. No larger recommendation boundary
or score floor is inferred. Actual EVOLVEpro recommendation-file provenance remains
a separate applicability gate; the ESM2/DMS pilot below does not reproduce an
EVOLVEpro recommendation round.

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
feature count is not functional diversity or fitness. The immediate application
gate is the actual EVOLVEpro candidate-file boundary and intended experimental
budget. General homolog application integration requires the RPC, certificate,
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

## Validation record

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
