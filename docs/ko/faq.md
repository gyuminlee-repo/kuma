# FAQ

## UniProt 검색에서 유사도 낮은 결과만 뜨는 이유?
EBI BLAST API는 contact 이메일을 요구함. 미설정 시 gene-name 텍스트 검색으로 fallback되어 homolog가 아닌 단백질들이 올라옴. `KURO_CONTACT_EMAIL` 환경변수 또는 `~/.kuro/config.json`에 `contact_email` 설정 — [설정](configuration.md).

## 변이를 960개 이상 쓸 수 있나?
가능. v1.33.6부터 상한 10,000 (약 100 플레이트). Parameter 패널에서 **Mutations** 값 조정.

## KURO가 받는 파일 포맷?
서열: `.gb`, `.gbk`, `.gbff`, `.dna` (SnapGene), `.fa`, `.fasta`. 변이 목록: 일반 텍스트 또는 EVOLVEpro CSV.

## 인터넷 필요?
UniProt / BLAST / AlphaFold 조회만 필요 (선택). 핵심 프라이머 설계는 완전 오프라인 동작.

## 다중 플레이트 레이아웃은 어떻게 배치?
입력 순서대로 96웰 단위로 할당. 공유되는 reverse 프라이머는 플레이트별 중복 제거. [플레이트 맵](plate-map.md) 참고.

*추가 Q&A 예정.*
