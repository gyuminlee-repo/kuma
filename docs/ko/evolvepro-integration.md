# EVOLVEpro 연동 가이드

## 개요

KUMA는 [EVOLVEpro](https://doi.org/10.1126/science.adr6006) (Jiang et al.
2025, Science) GUI 래퍼를 선택 기능으로 제공한다. EVOLVEpro는 directed
evolution을 위해 단백질 변이체를 스코어링하는 ML 모델이다. KUMA는 사용자가
직접 설치한 EVOLVEpro conda 환경을 subprocess로 호출하고, 표준출력을 파싱해
진행 상황을 표시한다.

**KUMA는 EVOLVEpro를 번들·재배포·수정하지 않는다.** EVOLVEpro는 MIT TLO
Internal Research EULA (학술·비상업 용도)로 배포된다. 사용자는 EVOLVEpro를
직접 설치하면서 EULA를 직접 수락해야 한다.

## 사전 요구 사항

- 16 GB RAM (ESM-2 650M 모델 + working set 8 GB)
- 사용자 캐시 볼륨에 10 GB 여유 공간 (모델 가중치 + 중간 스코어링 산출물)
- 동작하는 `conda` 또는 `mamba`
- 첫 실행 시 네트워크 (ESM-2 가중치 약 2.5 GB 다운로드)

## 설치

1. 전용 conda 환경 `evolvepro` 생성:

   ```bash
   conda create -n evolvepro python=3.11 -y
   conda activate evolvepro
   ```

2. EVOLVEpro 업스트림 가이드에 따라 설치한다. 업스트림 설치 프로그램이
   요청하는 MIT TLO Internal Research EULA는 사용자가 직접 수락해야 한다.
   KUMA가 대신 동의하지 않는다.

3. 셸에서 설치 확인:

   ```bash
   conda run -n evolvepro evolvepro --help
   ```

   명령이 CLI help를 출력하면 KUMA가 해당 환경을 감지한다.

## 첫 실행

EVOLVEpro 패널에서 **Run** 버튼을 처음 누르면 EVOLVEpro가 ESM-2 650M
체크포인트(약 2.5 GB)를 다음 경로로 다운로드한다.

```
~/.cache/torch/hub/checkpoints/esm2_t33_650M_UR50D.pt
```

다운로드는 EVOLVEpro subprocess 내부에서 진행되고, KUMA는 "Loading ESM-2
model" 단계만 표시한다. 캐시 디렉토리당 1회만 발생한다.

## KUMA에서 EVOLVEpro 사용

1. KUMA 메인 윈도우에서 EVOLVEpro 패널 열기.
2. 온보딩 카드가 `evolvepro` conda 환경을 감지해 `env_found`, 버전, 가중치
   캐시 상태를 보고한다.
3. Run 폼 입력:
   - **Input CSV**: 변이체 표 (컬럼 스키마는 EVOLVEpro 업스트림 형식)
   - **WT sequence**: 야생형 단백질 서열 (amino acid)
   - **Rounds**: evolution 라운드 수 (1-10)
   - **Top N**: 보존할 top 변이체 개수
   - **Output directory**: EVOLVEpro 출력 디렉토리
4. **Run** 클릭. 5단계 진행: detect, loading, scoring, selecting, done.
5. 완료 후 top 변이체 표가 렌더링된다.

## 오프라인 모드

첫 실행 시 네트워크 없이 EVOLVEpro를 실행하려면 ESM-2 가중치를 다음 경로에
수동 배치한다.

```
~/.cache/torch/hub/checkpoints/esm2_t33_650M_UR50D.pt
```

파일 SHA-256은 업스트림 체크포인트와 일치해야 한다. KUMA는 파일 존재만
확인하고 해시는 검증하지 않는다.

## 문제 해결

| Error kind | 원인 | 해결 |
| --- | --- | --- |
| `env_not_found` | PATH에 conda 없음 또는 `evolvepro` env 미존재 | `conda env list`에 `evolvepro` 출력 확인 |
| `network` | PyTorch hub / HuggingFace 접근 불가 | 오프라인 모드 (수동 가중치 배치) 사용 |
| `disk_full` | 캐시 볼륨 공간 부족 | `~/.cache/` 호스팅 볼륨에 10 GB 확보 |
| `permission` | KUMA가 출력 디렉토리에 쓰기 불가 | 쓰기 가능한 출력 디렉토리 선택 |
| `runtime_error` | EVOLVEpro subprocess 크래시 | UI 표시 stdout/stderr 전체 로그 확인 |

## 라이선스 고지

EVOLVEpro는 MIT TLO Internal Research EULA로 배포된다. EVOLVEpro를 conda
환경에 설치한다는 것은 사용자가 MIT TLO와 직접 그 EULA에 동의함을 의미한다.
KUMA의 역할은 사용자 설치본을 subprocess로 호출하는 것뿐이다. KUMA 자체는
GPLv2 (`LICENSE` 참고).
