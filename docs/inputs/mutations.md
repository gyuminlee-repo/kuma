# 변이 입력 파일

KURO Step 2 의 세 가지 입력 모드.

## Text mode

한 줄에 한 변이. `Q232A` 형식.

```
Q232A
K15R
T100S
```

빈 줄·주석(`#`) 무시.

## EVOLVEpro CSV

`df_test.csv` 형식. 최소 컬럼:

| 컬럼 | 의미 |
|---|---|
| `variant` | `Q232A` 등 변이 표기 |
| `y_pred` | 예측 fitness score |

추가 컬럼은 무시. score 내림차순 정렬 후 top-N 자동 선택.

## Selection mode 옵션 (EVOLVEpro)

| 옵션 | 효과 |
|---|---|
| Top-N by score | 상위 N 개 선택 |
| Position diversity | position 당 변이 N 개 제한 (Grantham tie-break) |
| Domain diversity | InterPro domain 비례·균등 quota |
| Pareto diversity | greedy maximin position spread |
| Entropy-guided (β) | y_pred entropy weight (Pareto 필요) |
| σ-Adaptive Pool | round 기반 K·entropy 자동 보정 |

position 1 (개시코돈, initiator Met) 변이는 치환 시 단백질 발현이 사라지므로 EVOLVEpro 결과 로드 단계에서 자동 제외된다. 제외된 변이 목록과 개수는 Design Report 에 표시된다.
