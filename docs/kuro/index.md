# KURO — 6-step 워크플로우

KURO 는 6개 step 으로 구성된 linear wizard 이다. 왼쪽 Workflow Rail 에서 step 을 자유롭게 클릭할 수 있고, 하단 Next 버튼은 누락 입력이 있을 때 안내 Dialog 를 띄운다.

```
1. Load        →  서열 + 유전자 + organism 선택
2. Mutation    →  text / EVOLVEpro 입력
3. Parameters  →  polymerase / codon strategy / Tm 범위
4. Submit      →  Design summary 카드 + Run Design
5. Output      →  per-mutation 결과 표 + 우측 DesignReportInspector
6. Export      →  xlsx / Echo / JANUS / plate map
```

<!-- TODO: insert screenshot of KURO 6-step rail -->

## v0.9.2.x 패치에서 바뀐 점

- **Sidebar 자유 navigate**: 어떤 step 이든 즉시 클릭 이동. prerequisite 미충족 step 은 빈 화면이 아닌 empty-state 메시지를 보여준다.
- **Next 버튼**: 필수 입력 누락 시 validation Dialog. sidebar 클릭은 차단하지 않는다.
- **Run Design 자동 advance**: 성공 시 popup 없이 `output.summary` 로 자동 이동.
- **DesignReportInspector**: Output 우측 고정 패널에 report 표시. 별도 step 아님.
- **DesignSummaryCard**: Submit step 상단에 sequence/mutation/parameter 핵심값 요약.

자세한 step 설명은 좌측 메뉴에서 step 별 페이지를 참고한다.
