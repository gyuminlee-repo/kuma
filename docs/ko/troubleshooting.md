# 트러블슈팅

## Sidecar process exited

Python sidecar가 기동 또는 RPC 호출 중 크래시. `~/.kuma/kuro/crash.log`에서 traceback 확인.

흔한 원인:
- PyInstaller 번들에 모듈 누락 (드물게 `ModuleNotFoundError` 보고)
- 서열 파일에 유효하지 않은 문자 포함
- 안티바이러스가 바이너리 차단

## UniProt: no matching entries / 유사도 낮은 hit

BLAST에 이메일 필요. `KURO_CONTACT_EMAIL` 또는 `~/.kuma/kuro/config.json`의 `contact_email` 설정 — [설정](configuration.md). v1.33.6+는 기본값이 있어 BLAST는 동작함. 여전히 유사도 낮으면 BLAST 자체 실패 (인터넷·EBI 상태 확인).

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

- **reverse, 최근접 Tm이 창 위**: 가장 짧은 합법 reverse가 이미 너무 뜨겁다. GC-rich 구간에서 흔하다. 닿는 손잡이는 둘이고 GC가 극단이면 둘 다 닿지 못한다. **Tm tolerance**는 ±10 °C에서 막힌다. reverse **프라이머 길이** 하한은 파라미터의 `R` 칸에서 직접 내릴 수 있고 기본값은 19-27 bp다. 자동 완화가 실패를 보고하기 전에 이미 두 축을 모두 시도하며 길이 하한을 18 nt 아래로는 내리지 않는다. 18은 이 프로젝트가 스스로 지키는 bench rule이다. 둘 다 거치고도 실패하면 설정이 아니라 서열의 여유가 없는 것이다.
- **reverse, 최근접 Tm이 창 아래**: 가장 긴 합법 reverse도 여전히 차갑다. AT-rich 구간이다. 이때도 tolerance 상향이 듣는다.
- **forward**: 대개 경계 문제다. 코돈 하류 염기가 부족하다.
- **overlap**: 시도한 길이 범위 어디에서도 overlap 창에 못 들어온다.
- **full overlap**: 프로파일의 길이 하한이 타깃 Tm이 허용하는 것보다 높다. Q5 SDM이 기본으로 full overlap 모드다.

실패 원인은 forward·reverse·overlap 단계별 진단으로 확인한다.

## 변이 수 상한 초과

v1.33.6에서 10,000으로 상향. 그 이상이면 run 분할.

## 문제를 보고할 때

위 항목으로 풀리지 않으면 메뉴 막대의 **진단** 으로 진단 파일을 만들어 첨부한다. 화면 문구를 옮겨 적는 것보다 정확하다. 저장 후 그 폴더가 열리고 외부 전송은 없다.

`run` 절에 마지막 설계 실행의 요청 파라미터(중합효소, 길이 범위, Tm 목표와 `tol_max`, GC 범위, `overlap_mode`, `strict_offtarget`, `auto_relax`)와 성공·실패 개수, 실패한 변이의 이름과 사유가 들어간다. 사유 문장이 어느 단계에서 무엇이 창 밖이었는지 말하므로 이 절만으로 위 항목 대부분을 판정할 수 있다. 그 밖에 앱 버전과 운영체제, 진행 메시지 50줄, 에러 바운더리 기록이 들어간다.

서열, 템플릿 경로, 프로젝트 이름, 성공한 변이 목록은 빠진다. 변이 표기 파싱 실패는 그 줄을 인용하고 야생형 불일치는 WT 코돈 3염기를 적으므로 그 둘은 남으며, 라벨과 사유 모두 길이 상한에서 잘리고 잘린 사실이 값에 표시된다.

`"status": "no-run-data"` 는 설계를 돌리지 않았거나 입력이 바뀌어 결과가 폐기된 상태다. `"request": null` 은 저장한 프로젝트에서 복원한 결과로, 프로젝트 파일이 설계 요청을 담지 않아 생긴다. 파라미터가 필요하면 같은 설정으로 한 번 다시 돌린 뒤 파일을 만든다.
