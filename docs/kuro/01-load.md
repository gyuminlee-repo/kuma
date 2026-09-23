# Step 1. Sequence Load

서열 파일을 로드하고 target gene · organism 을 지정한다.

## 입력

| 항목 | 포맷 | 필수 |
|---|---|---|
| 서열 파일 | GenBank `.gb/.gbk/.gbff`, SnapGene `.dna`, FASTA `.fa/.fasta/.fna` | 필수 |
| Target gene | 파일에서 자동 추출 후 dropdown 선택 | 필수 (multi-CDS 일 때) |
| Organism | 내장 codon table 5종(`kuma_core/kuro/resources/codon_tables/`)과 `~/.kuma/kuro/codon_tables` 의 사용자 표. 목록은 `list_organisms` RPC 가 두 출처를 합쳐 반환한다 | 필수 (codon table 결정) |

## 동작

GenBank는 첫 레코드의 서열과 CDS만 불러온다. 뒤쪽 레코드의 유전자를 설계하려면 해당 레코드를 flanking template과 함께 별도 GenBank 파일로 내보낸다. 서로 다른 레코드의 서열과 CDS 좌표를 섞지 않는다.

1. 드래그앤드롭 또는 Browse 로 서열 로드.
2. UniProt BLAST 자동 트리거 (network 동의 필요).
3. AlphaFold Cα 좌표 EBI API 에서 fetch (`consent_alphafold` 동의).
4. Sequence Map 패널에 CDS / domain / mutation 위치 SVG 가 표시된다.
5. Organism 은 서열 annotation 이 아는 균주 이름을 적고 있으면 자동 선택된다. 목록 마지막의 `Add organism...` 이 코돈 표 대화상자를 연다.

## Organism 과 코돈 표

설계에 쓰는 코돈 표를 고르는 자리다. 내장 5종(ecoli, bsubtilis, hsapiens, mextorquens, scerevisiae) 외의 균주는 사용자가 직접 넣는다. 세 경로가 있다.

1. `~/.kuma/kuro/codon_tables` 에 `<key>.json` 을 놓고 Settings → Codon tables 의 `Refresh` 를 누른다. `.json` 을 뗀 파일 이름이 key 가 된다. 같은 폴더의 `TEMPLATE.json.txt` 와 `README.txt` 가 포맷 정본이다.
2. `Add organism...` → `Import a table file` 탭에서 kuma 표(JSON), 3열 CSV, EMBOSS `cusp` 출력, Kazusa 페이지 붙여넣기 중 하나를 읽는다. 검사 결과와 digest 를 먼저 보여 주고 설치 여부를 묻는다.
3. `Add organism...` → `Compute from a genome` 탭에서 GenBank(`.gb/.gbk/.gbff`) 또는 CDS FASTA 의 코돈을 직접 센다. 센 CDS 수와 제외 사유를 함께 보고한다.

genetic code 는 1 또는 11 만 받고 내장 key 는 덮을 수 없다. 거부된 파일은 Settings 에 사유와 함께 나열된다. 설계는 표의 key 와 digest 를 기록하므로 그 표가 없는 컴퓨터에서 프로젝트를 열면 프로젝트가 품은 사본을 설치할지 묻는다.

<!-- TODO: insert screenshot of Sequence Load step -->

## v0.9.2.x 변경

- Sidebar 의 mutation/params step 을 미리 클릭해도 차단되지 않는다 (자유 navigate). 단, 해당 step 은 "Load a sequence file first" empty state 를 표시한다.
- Next 클릭 시 서열 미로딩이면 validation Dialog: "Sequence file is required".

## 다음

→ [Step 2. Mutation Input](02-mutation.md)
