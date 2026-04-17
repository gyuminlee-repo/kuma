# UniProt과 AlphaFold

![UniProt 후보 목록](../screenshots/07-uniprot-candidates.png)

CDS 선택 후 KURO가 UniProt을 검색하여 설계를 보강:

## BLAST 기반 매칭

CDS 번역 서열을 UniProt Swiss-Prot에 대해 EBI BLAST 수행. 상위 hit의 identity가 **≥ 95 %일 때만 자동 선택**; 그 미만이면 후보 목록을 보여주고 사용자가 수동 선택.

> **Contact 이메일 필수.** EBI는 이메일 없는 BLAST 요청을 거부함. `KURO_CONTACT_EMAIL` 환경변수 또는 `~/.kuro/config.json`의 `contact_email` 설정. [설정](configuration.md) 참고.

## 직접 accession 조회

GenBank 파일에 `db_xref="UniProtKB/..."` qualifier가 있으면 해당 entry를 직접 가져와 첫 번째 후보로 사용.

## Gene name fallback

BLAST 실패 시 UniProt gene-name 검색 시도 — 서열이 많이 divergent한 경우 유사도 낮은 매치만 나올 수 있음.

## AlphaFold 구조 배지

각 후보에 **AF** 배지 표시 (AlphaFold 예측 구조 존재 시). 후보 선택 시 Cα 좌표 다운로드 트리거 → 3D Pareto diversity에 사용 ([다양성 전략](diversity-strategies.md)).

*스텁 — 후보 패널 스크린샷 추가 예정.*
