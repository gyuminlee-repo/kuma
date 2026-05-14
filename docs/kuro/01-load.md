# Step 1. Sequence Load

서열 파일을 로드하고 target gene · organism 을 지정한다.

## 입력

| 항목 | 포맷 | 필수 |
|---|---|---|
| 서열 파일 | GenBank `.gb/.gbk/.gbff`, SnapGene `.dna`, FASTA `.fa/.fasta/.fna` | 필수 |
| Target gene | 파일에서 자동 추출 후 dropdown 선택 | 필수 (multi-CDS 일 때) |
| Organism | `ecoli` / `bsubtilis` / `scerevisiae` | 필수 (codon table 결정) |

## 동작

1. 드래그앤드롭 또는 Browse 로 서열 로드.
2. UniProt BLAST 자동 트리거 (network 동의 필요).
3. AlphaFold Cα 좌표 EBI API 에서 fetch (`consent_alphafold` 동의).
4. Sequence Map 패널에 CDS / domain / mutation 위치 SVG 가 표시된다.

<!-- TODO: insert screenshot of Sequence Load step -->

## v0.9.2.x 변경

- Sidebar 의 mutation/params step 을 미리 클릭해도 차단되지 않는다 (자유 navigate). 단, 해당 step 은 "Load sequence first" empty state 를 표시한다.
- Next 클릭 시 서열 미로딩이면 validation Dialog: "Sequence file required".

## 다음

→ [Step 2. Mutation Input](02-mutation.md)
