# 디자인 리포트

![디자인 리포트 다이얼로그](../screenshots/16-design-report.png)

설계 후 요약 다이얼로그. 설계 성공 시 자동 표시, Help 메뉴 → *Design Report*로도 열림.

## 섹션

1. **입력 요약**: 서열 이름, 유전자, 변이 수, 모드 (text / EVOLVEpro)
2. **파라미터 스냅샷** — 폴리머레이즈, Tm / GC / 길이, 코돈 전략
3. **파이프라인 통계** (EVOLVEpro 모드에서만) — 단계별 counts (Step 1 top-N, Step 2 diversity, Step 3 Pareto/entropy)
4. **도메인 통계** — 도메인별 픽 수 vs quota
5. **Rescue 통계** — 각 tolerance 단계에서 rescue된 프라이머 수
6. **Failures** — 모든 rescue 시도 실패한 변이와 사유 목록

## 활용

설계가 실제로 수행한 내용을 감사 가능한 기록으로 제공 — 실험노트 기재, 예상치 못한 플레이트 구성 디버깅에 유용.

*스텁 — 리포트 스크린샷 추가 예정.*
