# KURO — Kernel for Upstream Recombination Oligodesign


**한국어** | [English](README.md)

Gibson Assembly 기반 SDM 프라이머 배치 설계 데스크톱 앱.

![KURO Overview](docs/kuro_overview.png)

https://github.com/user-attachments/assets/f95e65ca-22d2-4479-a06b-8dcd553571be

변이 목록(텍스트/EVOLVEpro CSV)과 템플릿 시퀀스(GenBank/SnapGene)를 입력하면, overlap extension 방식의 SDM 프라이머 쌍을 자동 설계한다.

## 주요 기능

- **EVOLVEpro CSV 입력**: EVOLVEpro 출력 CSV 로드 → y_pred 내림차순 정렬 → 설정 개수만큼 자동 선정. **위치 다양성(position diversity)** 필터로 아미노산 위치당 최대 N개 제한 가능. **도메인 다양성(domain diversity)** 필터로 단백질 구조 도메인 간 분산 선택 (InterPro/Pfam 자동 조회 또는 수동 입력). **Pareto 다양성** 으로 MODIFY 방식의 위치 분산 최대화
- **배치 변이 파싱**: `Q232A` 형식의 변이 목록 → 코돈 위치 자동 계산 + WT 코돈 검증
- **코돈 전략 선택**: Min. changes (WT 대비 최소 염기 변이) 또는 Optimal (E. coli 최적 코돈) 중 선택 가능
- **Overlap upstream 설계**: overlap 영역이 mutation codon 바로 앞(upstream)에 위치 (EVOLVEpro 방식)
- **Tm 계산**: SantaLucia 1998 고정 (폴리머라제 무관). 기본 타겟 Fwd 62°C, Rev 58°C, Overlap 42°C. Advanced Options에서 변경 가능
- **점진적 Tm tolerance**: Fwd/Rev 각각 ±0.5°C부터 시작, ±0.5씩 독립 확장 (최대 ±3.0°C)
- **GC% 범위**: 기본 40-60% (Advanced Options에서 변경 가능). 범위 밖 프라이머에 패널티 부여
- **프라이머 길이 제한**: Fwd/Rev min/max 길이 제약 (Advanced Options에서 선택적 활성화)
- **Hairpin / Homodimer 검증**: primer3 calc_hairpin/calc_homodimer로 이차 구조 체크. Tm, dG(kcal/mol) 표시
- **합성 품질 점수**: IDT/Twist 가이드라인 기반 올리고 합성 난이도 평가 (0-100). Homopolymer, GC-rich 연속, 디뉴클레오타이드 반복, 극단 GC% 감점
- **Sequence Map**: 접이식 SVG 선형 CDS 맵. 돌연변이 위치, 도메인 영역, 밀도 히스토그램으로 클러스터링 감지
- **컬럼 정렬**: 모든 결과 컬럼 정렬 가능 (y_pred, 합성 점수 포함). Plate map export에도 정렬 순서 반영
- **후보 비교 및 교체**: 프라이머 서열 클릭 시 후보 비교 팝오버 (candidate 1개여도 클릭 가능). 수동 교체 시 결과 테이블에 amber 하이라이트
- **커스텀 프라이머 평가**: 후보 팝오버에서 직접 서열 입력 → Tm, GC%, hairpin, off-target 즉시 계산
- **실패 돌연변이 재시도**: 실패한 mutation 클릭 → Tm/GC%/길이/tolerance 조절 → 조절된 파라미터로 재설계 → 후보 선택
- **실패 시 자동 채움(Fill on failure)**: 활성화 시(기본 꺼짐) 일부 mutation 실패해도 추가 후보로 요청 수만큼 자동 채움
- **Off-target 검증**: template sense/antisense strand에서 비특이적 결합 자동 검출. OT `!!` 클릭 시 결합 위치·strand·Tm 상세 팝오버
- **96-well Plate Map**: Fwd/Rev 쌍 연동 플레이트. 96개 초과 시 multi-plate 슬라이드 (Plate N Fwd ↔ Plate N Rev). 테이블 정렬 연동
- **Workspace 저장/불러오기**: 파라미터 + 설계 결과를 `.kuro.json`으로 저장하여 세션 간 이동 가능
- **데스크톱 GUI**: Windows / macOS / Linux 크로스플랫폼 앱

## 설치

[Releases](https://github.com/gyuminlee-repo/KURO/releases) 페이지에서 최신 인스톨러를 다운로드한다.

- **Windows**: `KURO_x.x.x_x64-setup.exe` (NSIS 인스톨러)

## 사용법

1. 시퀀스 파일 로드 (GenBank .gb / SnapGene .dna)
2. Target Gene 드롭다운에서 타겟 유전자 CDS 확인 (자동 선택)
3. 변이 입력 (텍스트 직접 입력 또는 EVOLVEpro CSV 로드)
4. 코돈 전략 선택 (Min. changes / Optimal)
5. (선택) Advanced Options에서 Tm 타겟, GC% 범위, 프라이머 길이 조정
6. **Design Primers** 클릭
7. Fwd/Rev 서열 클릭 → 후보 비교 팝오버에서 교체 가능
8. HP 컬럼 클릭 → hairpin/homodimer 상세 (Tm, dG)
9. File → Export Excel / Save Workspace

상세 설명은 [사용자 가이드](USER-GUIDE.ko.md) 참조.

## 라이선스

[GPL v2](LICENSE)
