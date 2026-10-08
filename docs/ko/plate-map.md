# 플레이트 맵

![단일 플레이트](../screenshots/05-plate-map.png)

설계된 프라이머 셋을 96웰 그리드로 렌더. 설계 완료 후 표시.

## 탭

- **Forward** — 녹색 그리드
- **Reverse** — 주황 그리드, 파란색 웰은 다수 변이에서 공유되는 항목

## 레이아웃

웰 순서: column-major A1 → H1 → A2 → … Reverse 프라이머가 여러 변이에 공유되면 플레이트별 1회만 배치되고 forward 쌍에서 참조.

공유 웰은 반응 수만큼 반복 흡입되므로 필요한 양이 1회분보다 많다. 액체 핸들러 `.xlsx` 의 `layout` 시트 하단 **Reverse primer usage** 표에 소스 웰별 공유 횟수와 총 transfer 소요량(공유 횟수 × 회당 부피)이 표기된다. 이 값은 기기 dead volume 을 포함하지 않으므로 실제로 채울 양은 여기에 사용 labware 의 dead volume 을 더한 값이다.

## 다중 플레이트 내비

![다중 플레이트 내비 (2장)](../screenshots/12-plate-multi.png)

96개 초과 시 탭 옆에 `‹ Plate N/M ›` 표시. 각 플레이트는 별도 그리드.

## Export Mapping

우측 끝 **Export Mapping...** 버튼으로 Echo / JANUS 액체핸들러 내보내기 다이얼로그 열기. [액체 핸들러 내보내기](export-liquid-handler.md).

## 하단 요약

그리드 아래: `Total: N fwd / M rev`. Reverse 탭일 때만 shared 범례 표시.
