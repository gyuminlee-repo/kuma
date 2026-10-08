# 설정

사용자별 설정은 `~/.kuma/kuro/`에 저장.

## `~/.kuma/kuro/config.json`

```json
{
  "contact_email": "you@example.com"
}
```

### `contact_email`

BLAST 와 InterProScan 작업을 EBI Job Dispatcher 에 제출할 때 보내는 제출자 주소다. 기본값은 없다. 주소가 없으면 kuma 는 EBI BLAST 와 InterProScan 제출을 건너뛴다. UniProt 검색은 BLAST 없이 나머지 조회(gene name, accession)로만 후보를 찾는다. 캐시에 없는 서열의 InterProScan 도메인 주석은 생략된다.

작업이 처음 주소를 필요로 할 때 kuma 가 입력 창으로 묻고 설정에 저장한다. 나중에 설정 > 네트워크 탭에서 바꿀 수 있다.

읽는 순서는 환경변수 `KURO_CONTACT_EMAIL`, 설정에 저장한 주소(`~/.kuma/preferences.json` 의 `network.contact_email`), 이 파일의 `contact_email` 이다. 처음 만난 비어 있지 않은 값을 쓴다. 그 값이 주소 형식이 아니면 없는 것으로 보고 뒤 단계는 보지 않는다.

## `~/.kuma/kuro/codon_tables`

사용자 코돈 표가 놓이는 폴더다. `.json` 파일 하나가 균주 하나다. 여기서 읽은 표는 내장 5종과 함께 타겟 유전자 옆 **Organism** 드롭다운에 나타난다. Settings → Codon tables 가 폴더 경로, 출처별 개수, **Open folder**, kuma 재시작 없이 폴더를 다시 읽는 **Refresh**, 그리고 거부된 파일과 그 사유를 보여 준다.

파일 이름이 key 를 정한다. `mextorquens_am1.json` 은 `mextorquens_am1` 균주로 설치된다. 같은 폴더의 `TEMPLATE.json.txt`, `README.txt`, `mextorquens_am1.json.txt` 는 참고용이며 표로 읽지 않는다. 마지막 파일은 빈 틀이 아니라 완성된 *M. extorquens* AM1 표이므로 `mextorquens_am1.json` 으로 이름만 바꾸면 그대로 설치된다.

표를 넣는 세 경로:

- `TEMPLATE.json.txt` 를 `<key>.json` 으로 복사하고 숫자를 바꾼 뒤 **Refresh**
- Organism 드롭다운 마지막의 **Add organism...** → *Import a table file* 탭. kuma 표(JSON), 3열 CSV, EMBOSS `cusp` 출력, Kazusa 코돈 사용 페이지 붙여넣기를 읽는다
- **Add organism...** → *Compute from a genome* 탭. GenBank(`.gb`, `.gbk`, `.gbff`)나 CDS FASTA 의 코돈을 kuma 가 직접 세어 표를 만든다

표에는 아미노산 20종과 stop 이 모두 있어야 하고 64개 코돈이 정확히 한 번씩 나와야 하며 한 아미노산의 빈도 합이 약 1 이어야 한다. NCBI genetic code 는 1 또는 11 만 받는다. 내장 key 9종(`ecoli`, `bsubtilis`, `hsapiens`, `scerevisiae`, `kphaffii`, `cgriseus`, `cglutamicum`, `aniger`, `pputida`)은 덮을 수 없으므로 고친 사본은 `ecoli_lab` 처럼 다른 key 로 넣는다. 부분 설치는 없고 파일 단위로 전부 받거나 전부 거부한다.

## `~/.kuma/kuro/custom_polymerases.json`

[커스텀 폴리머레이즈 에디터](custom-polymerase-editor.md)가 자동 관리. 수동 편집도 보존되지만 기본 프로파일 스키마 준수 필요.

## `~/.kuma/kuro/crash.log`

최근 50건의 sidecar 예외 기록 (timestamp, method, truncated traceback). `Sidecar process exited` 오류 보고 시 유용.
