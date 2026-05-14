# Step 5. Output Summary

per-mutation 설계 결과를 표 + 96-well plate map + 우측 DesignReportInspector 로 표시한다.

## Layout

```
┌──────────────────────────────────────┬─────────────────────┐
│  Result table (sortable)             │ DesignReport         │
│  + Plate map (96-well)               │ Inspector            │
│  + Sequence Map                      │ (고정 표시)          │
└──────────────────────────────────────┴─────────────────────┘
```

좌·우 영역은 `react-resizable-panels` splitter 로 폭 조절 가능 (v0.9.2.x D2). Inspector toggle 버튼으로 우측 영역을 접을 수 있다.

## Result table

- 모든 컬럼 sortable (y_pred, synthesis score 포함)
- Primer sequence 클릭 → Candidate comparison popover
- Failed mutation 클릭 → retry popover (median Tm / GC pre-fill + "Use suggestion" 버튼)

## DesignReportInspector (v0.9.2.x 신설)

`src/components/inspectors/kuro/DesignReportInspector.tsx`. 기존 `DesignReport.tsx` 본문이 재사용 가능한 `DesignReportContent` 로 분리되어 inspector 와 export 양쪽에서 사용된다.

내용:
- 전체 mutation 수 / success / failed
- Position rescue cascade 단계별 카운트 (🎯¹ length / 🎯² +GC / 🎯³ +mild Tm / 🎯⁴ strong / ↻¹ alt-variant / ↻² alt-position)
- Synthesis quality score 분포
- Off-target 검출 로그

## 다음

→ [Step 6. Export](06-export.md)
