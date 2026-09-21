# Licensing review findings, 2026-09-18

This is a record of unresolved distribution questions, not a legal clearance.
See [English checklist](en/license-compliance.md) and
[한국어 검토표](ko/license-compliance.md).

## xlwt 1.3.0

The published wheel omits its license document. The exact 1.3.0 release
[license document](https://github.com/python-excel/xlwt/blob/1.3.0/docs/licenses.rst)
contains not only BSD terms but also pyExcelerator advertising/acknowledgment
conditions and LGPL-derived portions. The version-bound supplement preserves
all of them, with the source blob and SHA256 recorded in
`scripts/license-supplements.json`.

Do not describe xlwt as unconditionally permissive from its BSD metadata alone.
Review the applicability and GPL compatibility of those portions, source delivery
and product acknowledgments before distribution. This maintenance change does
not resolve that rights question or replace the XLS writer.

## 한국어 요약

xlwt 1.3.0 wheel에는 고지 원문이 빠져 있다. 해당 릴리스 원문에는 BSD 조건 외에
pyExcelerator의 광고·저작자 표시 조건과 LGPL 유래 부분도 있어 모두 보존했다.
메타데이터의 BSD 표시만으로 무조건 허용적인 의존성이라고 설명하지 않는다.
배포 전 해당 부분의 적용 범위, GPL 호환성, 소스 제공과 제품 표시를 검토해야
한다. 이번 변경은 그 권리 문제를 해결하거나 XLS 출력기를 교체한 것이 아니다.

## primer3-py 2.3.0 and the noncommercial question, 2026-09-20

A research-only or noncommercial license was evaluated for KUMA and found
unavailable for the current build. `primer3-py` 2.3.0 is GPL version 2 with no
linking exception, is a hard runtime dependency, is imported at module level by
four `kuma_core` modules, and is named in the `collect_all` list of both
sidecar builds. Section 6 of GPL version 2 forbids further restrictions on
recipients, so the distributed combined work cannot carry a noncommercial term.
No other runtime component drives that outcome.

Do not describe KUMA anywhere as noncommercial or as prohibiting commercial
use. GPL version 2 permits commercial redistribution and requires the
redistributor to supply the complete corresponding source of the derivative
under the same terms. That obligation, not a use restriction, is what the
project license delivers. The import sites, the disqualifying evidence for the
other dependencies, and what a replacement project would have to revalidate are
recorded in [English checklist](en/license-compliance.md) and
[한국어 검토표](ko/license-compliance.md).

### 한국어 요약

KUMA 를 연구 전용이나 비상업 라이선스로 옮기는 안은 현재 구성에 적용할 수 없다.
`primer3-py` 2.3.0 이 링크 예외 없는 GPL version 2 이고 필수 런타임 의존성이며
`kuma_core` 네 모듈이 모듈 레벨에서 import 하고 두 사이드카 빌드가 이를 번들한다.
GPL version 2 의 6항이 추가 제한을 금지하므로 배포되는 결합 저작물에 비상업
조항을 붙일 수 없다. 다른 런타임 구성요소는 이 결론과 무관하다.

KUMA 를 비상업이라거나 상업적 이용을 금지한다고 표현하지 않는다. GPL version 2
는 상업적 재배포를 허용하되 재배포자에게 파생물의 대응 소스 전체를 동일 조건으로
제공할 의무를 지운다. 프로젝트 라이선스가 주는 것은 이용 제한이 아니라 그 의무다.
import 지점, 다른 의존성을 배제한 근거, 교체 시 재검증해야 할 범위는
[English checklist](en/license-compliance.md) 와
[한국어 검토표](ko/license-compliance.md) 에 기록했다.
