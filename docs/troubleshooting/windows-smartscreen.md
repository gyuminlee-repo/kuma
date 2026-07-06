# Windows "게시자: 알 수 없음" / SmartScreen 경고

## 증상

`kuma_x.y.z_x64-setup.exe` 실행 시:

> 이 파일이 일반적으로 다운로드되지 않기 때문에 Microsoft Defender SmartScreen은
> 이 파일이 안전한지 확인할 수 없습니다. … 게시자: 알 수 없음

## 원인

설치 파일에 **코드 서명(Authenticode)이 없어서**다. 악성 코드가 아니라 서명 인증서가
없기 때문에 나오는 경고이며, 모든 아티팩트는 태그 커밋에서 GitHub Actions로 공개
빌드된다. SmartScreen은 (1) 게시자(서명) 평판과 (2) 파일 해시 평판을 보는데, 서명이
없고 다운로드 이력이 적으면 경고가 뜬다.

## 실행 방법

경고 창에서 **추가 정보(More info) → 실행(Run anyway)**.

## 무결성 검증 (권장)

릴리즈에 첨부된 `SHA256SUMS.txt` 의 값과 다운로드한 파일의 SHA-256 해시를 비교한다.

```powershell
Get-FileHash .\kuma_x.y.z_x64-setup.exe -Algorithm SHA256
```

macOS / Linux:

```bash
shasum -a 256 <file>   # 또는 sha256sum <file>
```

출력된 해시가 `SHA256SUMS.txt` 의 해당 파일명 줄과 일치해야 한다.

## macOS

macOS 번들은 ad-hoc 서명만 되어(Apple Developer ID / notarization 없음) Gatekeeper
경고가 날 수 있다. 앱을 우클릭 → **열기**, 또는 **시스템 설정 → 개인정보 보호 및 보안**
에서 허용한다.

## 근본 해결 (선택)

경고를 완전히 없애려면 코드 서명이 필요하다. 비용/효과 순:

- **Azure Trusted Signing** (~$10/월): MS 신뢰 루트 체인, 사실상 즉시 경고 해소, CI 친화적.
- **EV 코드서명 인증서**: SmartScreen 즉시 통과(HSM 토큰이라 CI 배선 복잡).
- **OV 코드서명 인증서**: 게시자는 표시되나 평판은 다운로드 누적으로 시간이 걸림.

도입 시 Tauri v2 `bundle.windows` 서명(`certificateThumbprint` / `signCommand`)과
`build.yml` secret 배선이 필요하다.
