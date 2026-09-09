# 서열 입력 파일

KURO Step 1 · MAME Step 1.1 에서 사용하는 서열 파일 사양.

## 지원 확장자 (whitelist)

`python-core/sidecar_kuro/core.py:49-51` 기준:

| 카테고리 | 확장자 |
|---|---|
| FASTA / GenBank / SnapGene | `.fa .fasta .fna .dna .gb .gbff .gbk` |
| CSV / TSV | `.csv .tsv .txt` |
| Excel | `.xlsx` |

## GenBank (`.gb` / `.gbk` / `.gbff`)

- multi-CDS 지원. UI 의 gene dropdown 에서 target 선택.
- `cds_start` 는 `seqInfo.genes[].cds_start` 에서 자동 추출.
- features 의 `/gene=` / `/locus_tag=` 가 dropdown label.

## FASTA (`.fa` / `.fasta` / `.fna`)

- 단일 sequence 권장. multi-record FASTA 는 첫 record 사용.
- CDS 정보 없으므로 cds_start 를 UI 에서 수기 입력.

## SnapGene (`.dna`)

- snapgene-reader 로 파싱. GenBank 와 동등하게 multi-CDS 지원.

## Organism

값은 `kuma_core/kuro/resources/codon_tables/` 에 있는 JSON 파일 이름(확장자 제외)이다.
이 디렉토리가 정본이므로 여기에 목록을 고정하지 않는다.

- 표시 이름은 각 JSON 의 `name` 필드에서 온다.
- UI dropdown 은 `list_organisms` RPC 로 이 디렉토리를 조회한다 (`kuma_core/kuro/codon_table.py` 의 `list_organisms`).
- 설계 시점 검증(`python-core/sidecar_kuro/handlers/design.py`)도 같은 목록을 쓴다. 파일을 추가하면 양쪽에 함께 반영된다.
