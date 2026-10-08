# Step 6. Export

설계 결과를 외주 합성·liquid handler 포맷으로 내보낸다.

## 산출물

| 포맷 | 용도 |
|---|---|
| `primers.xlsx` | 전체 primer pair + Tm/GC/secondary structure |
| `expected_mutations.xlsx` | MAME 입력. `__kuma_meta__` 숨김 시트 포함 |
| Echo 525 transfer list | 384-well source plate + transfer xlsx |
| JANUS rack layout | Fwd/Rev 96-well rack + transfer xlsx |
| Macrogen order CSV | 외주 합성 form |
| 96-well plate map xlsx | 시각용 (table sort order 동기화) |

<!-- TODO: insert screenshot of Export step -->

## v0.9.2.x 변경

- Export step 헤더가 `Step 6: Export` 로 표시 (전체 1..6 단조 증가).
- 표 정렬 순서가 plate map · Echo · JANUS export 에 그대로 반영된다.

## 다음

KURO 작업 완료. 시퀀싱 결과가 돌아오면 같은 프로젝트 폴더의 [MAME 탭](../mame/index.md) 으로 이동한다.
