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
- 1-based vs 0-based? KURO 위치는 CDS 내 1-based
- 아이소폼 불일치? 서열에 해당하는 UniProt entry 확인

## Tm 조건 미충족 (FAIL 다수)

- **Tm targets** ±2 °C 확대
- Advanced Options에서 **Tm tolerance** (`tol_max`) 상향
- **Fill on Failure** 활성화로 버퍼 후보 활용

## CSV file missing required 'mutation' column

EVOLVEpro CSV는 정확히 `mutation`이라는 이름의 컬럼 필요 (대소문자 구분). 컬럼명 변경.

## No valid primer pair found within Tm tolerance

모든 후보 윈도우 실패. 확인:
- 타깃 잔기가 서열 경계 근처 (flanking 서열 부족)
- 극단적 GC context (폴리A/T 구간)
- Tm 범위 넓은 다른 폴리머레이즈 시도

## 변이 수 상한 초과

v1.33.6에서 10,000으로 상향. 그 이상이면 run 분할.
