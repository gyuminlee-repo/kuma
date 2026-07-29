# 트러블슈팅

## Sidecar process exited

Python sidecar가 기동 또는 RPC 호출 중 크래시. `~/.kuro/crash.log`에서 traceback 확인.

흔한 원인:
- PyInstaller 번들에 모듈 누락 (드물게 `ModuleNotFoundError` 보고)
- 서열 파일에 유효하지 않은 문자 포함
- 안티바이러스가 바이너리 차단

## UniProt: no matching entries / 유사도 낮은 hit

BLAST에 이메일 필요. `KURO_CONTACT_EMAIL` 또는 `~/.kuro/config.json`의 `contact_email` 설정 — [설정](configuration.md). v1.33.6+는 기본값이 있어 BLAST는 동작함. 여전히 유사도 낮으면 BLAST 자체 실패 (인터넷·EBI 상태 확인).

## "expected WT amino acid X at position N, but codon YYY encodes Z"

변이의 WT 문자가 해당 위치 CDS와 불일치.
- CDS 잘못 선택? 드롭다운에서 유전자 전환 — [유전자 선택](gene-selection.md)
- 1-based vs 0-based? Kuro 위치는 CDS 내 1-based
- 아이소폼 불일치? 서열에 해당하는 UniProt entry 확인

## Tm 조건 미충족 (FAIL 다수)

- **Tm targets** ±2 °C 확대
- Advanced Options에서 **Tm tolerance** (`tol_max`) 상향
- **Fill on Failure** 활성화로 버퍼 후보 활용

## CSV file missing required variant column

EVOLVEpro CSV는 `variant`, `variants`, `mutation`, `mutations`, `mutant`, `mutation_list` 중 하나의 컬럼명 필요 (대소문자 구분, 첫 매칭). 컬럼명을 위 중 하나로 변경.

## No valid primer pair

v0.13.22부터 실패 사유가 막힌 단계, 그 단계가 도달한 최근접 Tm, 타깃 창, 길이 제약을 함께 알려준다.

```
No valid primer pair - reverse: closest Tm 64.4C at 19 bp, outside 58+-4.0C (length 19-27 bp)
```

단계를 먼저 읽는다.

- **reverse, 최근접 Tm이 창 위**: 가장 짧은 합법 reverse가 이미 너무 뜨겁다. GC-rich 구간에서 흔하다. 길이 하한은 UI에서 못 내리므로 **Tm tolerance**를 올린다.
- **reverse, 최근접 Tm이 창 아래**: 가장 긴 합법 reverse도 여전히 차갑다. AT-rich 구간이다. 이때도 tolerance 상향이 듣는다.
- **forward**: 대개 경계 문제다. 코돈 하류 염기가 부족하다.
- **overlap**: 시도한 길이 범위 어디에서도 overlap 창에 못 들어온다.
- **full overlap**: 프로파일의 길이 하한이 타깃 Tm이 허용하는 것보다 높다. Q5 SDM이 기본으로 full overlap 모드다.

막는 단계는 예상과 다를 수 있다. IspS 95종 실행에서는 실패가 전부 reverse에서 나왔고 forward와 overlap이 원인인 경우는 하나도 없었다.

## 변이 수 상한 초과

v1.33.6에서 10,000으로 상향. 그 이상이면 run 분할.
