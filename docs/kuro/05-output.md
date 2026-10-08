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

## Candidate 3D structure analysis (v0.13.7)

Output 하단의 접이식 패널 (기본 접힘, 열 때만 3Dmol 로드). structure/UniProt accession 이 있으면 AlphaFold/PDB 구조를 불러오고, 없으면 PDB/CIF 업로드 fallback 으로 진행한다. 대상은 현재 design 후보 집합 (`evolveproSelectedVariants`), 없으면 ranked candidates 전체.

레이아웃 순서(위→아래): **툴바 → 3D viewer → Color legend → Structural Dispersion → Active site → Selected Positions/Positions by Domain**. 토글·색칠 조작 결과를 바로 위 viewer에서 즉시 확인할 수 있도록 뷰어와 컨트롤을 붙여 배치.

구성:
- **3Dmol viewer** — cartoon + variant sphere(y_pred 그라데이션) + active-site stick(주황) + binding-site sphere(마젠타). domain/pLDDT/plain 색칠 모드, surface, spin, fullscreen, PNG export.
- **Color legend** — viewer 바로 아래. 각 색의 의미를 현재 색칠 모드/표시 상태에 맞춰 표시하고, **행 클릭으로 3D 레이어 on/off** (variant / active-site / binding-site). backbone은 구조가 항상 보여야 하므로 토글 대상 제외.
- **Structural Dispersion 카드** — 선택 변이 위치들이 3D 공간에서 얼마나 뭉쳤는지/퍼졌는지를 무작위 matched-size 잔기 집합(null)과 비교. mean pairwise Cα 거리, null p05–p95, percentile(`P1`=강한 clustering, `P99`=강한 spread), classification, null 분포 히스토그램.
- **`?` 도움말 토글** — 카드/히스토그램/각 지표/legend에 인라인 설명(InlineHelp).
- **Selected Positions / Positions by Domain 표** — accession-frame 로 매핑된 위치, active/binding/pLDDT/domain.

**용어 주의 (binding site)**: 마젠타 sphere로 표시되는 것은 UniProt `Binding site` feature(리간드/기질/보조인자/금속이온 결합 잔기)다. **단백질-단백질 계면(interface)이 아니다.** 이전에 "Interface"로 표기했던 라벨은 `Binding site`로 정정됨(v0.13.7.2). 주황 stick은 UniProt `Active site`(촉매 잔기).

### 해석 원칙 — QC 보조이지 selection filter 가 아님

3D dispersion·pLDDT·active/interface overlay 는 **해석·QC 보조 지표**다. 후보 선정 게이트가 아니다.

- 구조를 못 이루는(저 pLDDT / disordered) 잔기라도 **변이 대상에서 자동 배제하지 않는다.** 후보 선정 권한은 EVOLVEpro `y_pred` 랭킹에 있다.
- 근거(비대칭 손익): 낭비되는 well 1개(bounded, ~1%) < 놓친 진짜 hot spot(그 라운드에서 회복 불가). ESM/EVOLVEpro 점수가 이미 저제약 위치를 낮게 랭크하므로 구조 필터는 대체로 중복이고, loop/동역학 유래 유익 변이를 잘라낼 위험이 있다.
- 예외는 “필터”가 아니라 좌표 정합성 문제다: transit peptide / tag / linker 처럼 **성숙 단백질에 없는 구간**은 애초에 변이 대상 좌표에서 제외한다.
- 저 pLDDT 위치가 top 에 올라오면 자동 배제가 아니라 사람이 이 패널로 보고 판단한다.

## 다음

→ [Step 6. Export](06-export.md)
