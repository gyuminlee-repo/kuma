# Licensing review findings — 2026-09-18

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
