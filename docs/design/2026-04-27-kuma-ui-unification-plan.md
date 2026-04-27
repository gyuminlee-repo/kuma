# kuma UI 통일성 개선 계획서

**작성일**: 2026-04-27
**대상**: `kuma` 셸과 그 안의 `kuro`, `mame` 탭
**핵심**: 두 서브툴을 똑같이 만들지 않는다. 같은 토큰 시스템 위에 얹어 한 제품으로 읽히게 한다.

---

## 1. 한 줄 결론

지금 문제는 기능 통합 부족이 아니라 시각 시스템 부재다. 4px 그리드와 토큰 16종을 먼저 고정하고, 그 위에서만 컴포넌트를 다시 깎는다.

근거는 두 가지다.
- `kuro`는 큰 radius(`rounded-[22px]`)와 강한 shadow를 기본으로 깐다. anti-patterns의 "모든 요소에 둥근 사각형 + 그림자", "border-radius > 16px"에 정면으로 걸린다.
- `mame`는 평평한 카드와 작은 radius로 같은 셸 안에서 다른 제품처럼 보인다. 양쪽 모두 미정의 변수(`--verdict-pass`, `--status-ready`, `text-2xs`, `h-statusbar`)를 무단 사용해, 토큰화 없이 손대면 임의값이 또 추가된다.

---

## 2. 현재 차이 (코드 기준)

진단 대상 파일은 다음과 같다 (경로는 repo 루트 기준).

- 셸: `src/screens/MainShell.tsx`
- `kuro` 메뉴/레이아웃: `src/components/layout/MenuBar.tsx`, `src/components/layout/AppLayout.tsx`
- `mame` 메뉴/레이아웃: `src/components/mame/layout/MenuBar.tsx`, `src/components/mame/layout/MameAppLayout.tsx`
- 토큰: `src/index.css`, `tailwind.config.js`

| 영역 | `kuro` | `mame` | 문제 |
|---|---|---|---|
| 메뉴바 | `px-5 py-3` 가변 + 검정 pill 브랜드 배지 | `h-11 px-4` 고정 + 이모지 + `kuro flow` 배지 | 높이·여백·브랜드 표기 모두 불일치 |
| 상태바 | `h-6 px-3 text-xs` | `h-statusbar px-4 text-2xs` + 빨간 pill | 높이·밀도·에러 표현 불일치. `text-2xs`/`h-statusbar`는 정의되지 않음 |
| 사이드바 외곽 | `rounded-[22px]` + 강한 shadow + 카드 중첩 | `rounded-lg` 단일 컨테이너 | radius 폭이 두 배, 깊이감 다름 |
| 패널 헤더 | 대문자 `SEQUENCE CONTEXT`/`DESIGN OUTPUT`/`PLATE PLAN` | sentence case `Verdict Table` | 어휘·정렬 불일치 |
| 어조 | `KURO` 대문자, 설명형 문장 | 소문자 `mame`, 🐟 이모지 | 같은 셸에서 두 정체성 충돌 |
| 의미 색 | `--destructive` 만 사용 | `--verdict-pass/fail`, `--status-ready/connecting/error` (미정의) | 색맹 친화 X, 토큰 누수 |

구조적 차이(메인 패널 3분할 vs SummaryRow+Verdict)는 도메인이 다르므로 보존한다. 시각 문법 차이만 제거한다.

---

## 3. 디자인 원칙

다음 다섯 가지가 이후 모든 결정을 강제한다.

1. **4px 그리드만 쓴다.** 모든 spacing·height·radius는 `4·8·12·16·20·24·28·32·36·40·48` 안에서 고른다. 22, 11, 13 같은 4의 배수가 아닌 임의 수치는 금지한다. 타이포는 별도로 §4.2에서 세 단계로 고정한다.
2. **그림자는 떠 있는 것에만 준다.** 패널·카드·사이드바는 1px border로 구분한다. 다이얼로그·드롭다운·토스트만 shadow를 가진다.
3. **radius는 두 단계.** 컨테이너 `12px`, 컨트롤 `8px`. pill은 `9999px` 한정. 16px를 넘기지 않는다.
4. **의미 색은 4종으로 닫는다.** success / warning / error / info 외 추가 금지. 색만으로 의미를 전달하지 않는다(반드시 도형 또는 아이콘 병행).
5. **브랜드 계층 고정.** 1차는 `kuma`, 2차는 `Kuro`/`Mame`. 이모지·장식 배지·대문자 로고 표기 전부 제거. 화면당 Primary 버튼 1개 한도.

---

## 4. 공통 토큰

`src/index.css`에 다음 16종을 추가한다. 코드는 Tailwind 유틸 또는 `var()` 둘 중 하나로만 접근하고 직접 px 작성을 금지한다(§4.4).

### 4.1 크기·radius·shadow

```css
/* size */
--header-h: 48px;          /* kuma 제품 헤더 */
--menubar-h: 40px;         /* 서브툴 메뉴 */
--statusbar-h: 24px;
--sidebar-w: 320px;
--control-h: 32px;         /* 입력·메뉴·보조 버튼·표 행 */
--control-h-primary: 36px; /* CTA, Run 계열 */

/* radius */
--radius-container: 12px;
--radius-control: 8px;

/* shadow — floating only */
--shadow-floating: 0 12px 32px rgba(24,24,27,0.10);
```

### 4.2 타이포 (3단계)

```css
--text-title: 13px;   /* 패널 제목, font-semibold */
--text-body: 14px;    /* 본문, 표 셀, 입력값 */
--text-caption: 12px; /* 상태, eyebrow, 보조 설명 */
```

본문 컴포넌트는 `var(--text-body)` 또는 Tailwind `text-sm`/`text-xs` 둘 중 하나로만 쓴다. `text-[13px]` 같은 임의 px 작성은 금지한다.

### 4.3 의미 색 (4종)

oklch는 P3 디스플레이 호환과 균일한 명도를 보장한다.

```css
--color-success: oklch(0.65 0.15 145); /* sidecar ready, verdict pass */
--color-warning: oklch(0.72 0.15 75);  /* partial result, rescue 발동 */
--color-error:   oklch(0.55 0.20 25);  /* error text, verdict fail, retry */
--color-info:    oklch(0.60 0.12 250); /* progress, info toast */
```

기존 `--verdict-pass/fail`, `--status-ready/connecting/error`는 의미 색으로 통합 흡수해 별도 정의를 폐기한다(§6.2 참조).

### 4.4 motion (3종)

```css
--duration-fast: 150ms;  /* hover, focus ring */
--duration-base: 200ms;  /* dropdown, panel expand, toast */
--easing-standard: cubic-bezier(0.4, 0, 0.2, 1);

@media (prefers-reduced-motion: reduce) {
  :root { --duration-fast: 0ms; --duration-base: 0ms; }
}
```

### 4.5 Tailwind 노출

`tailwind.config.js`의 `theme.extend`에 위 토큰을 명시 매핑해 유틸 클래스로 직접 사용 가능하게 한다.

```js
theme.extend = {
  height:       { header: 'var(--header-h)', menubar: 'var(--menubar-h)',
                  statusbar: 'var(--statusbar-h)', control: 'var(--control-h)',
                  'control-primary': 'var(--control-h-primary)' },
  width:        { sidebar: 'var(--sidebar-w)' },
  borderRadius: { container: 'var(--radius-container)', control: 'var(--radius-control)' },
  fontSize:     { title: 'var(--text-title)', body: 'var(--text-body)', caption: 'var(--text-caption)' },
  colors:       { success: 'var(--color-success)', warning: 'var(--color-warning)',
                  error: 'var(--color-error)', info: 'var(--color-info)' },
  transitionDuration: { fast: 'var(--duration-fast)', base: 'var(--duration-base)' },
}
```

이후 코드는 `h-control`, `w-sidebar`, `text-title`, `text-success`, `duration-fast` 같은 클래스로만 토큰을 쓴다. `h-8`, `text-[13px]` 같은 직접값 사용 금지.

### 4.6 배제

- `--shadow-panel` 없음 → 기본 패널은 border-only.
- `control-h-sm/md/lg` 3종 없음 → 32/36 두 종으로 충분.
- `--content-gap` 없음 → 그리드/플렉스 `gap-3`(12px), `gap-4`(16px) 직접 사용.

---

## 5. 셸 계층

`MainShell`을 공통 프레임의 주인으로 끌어올린다. 탭 내부 `MenuBar`는 "서브툴 메뉴"로 강등한다.

```
[ kuma 헤더 (48px) — 제품명 · 프로젝트 · 탭 스위처 ]
[ 서브툴 메뉴 (40px) — Kuro|Mame · File/Edit/Help · 모드 badge ]
[ 본문 — 사이드바 320px + 메인 ]
[ 상태바 (24px) — 메시지 · 요약 slot · sidecar 상태 ]
```

위계는 높이 차이로 1차 표현한다(`48 > 40 > 24`). 헤더는 제품 정보, 서브툴 메뉴는 도구 액션, 상태바는 시스템 메시지로 정보 종류도 분리한다. 배경은 두 줄 모두 `bg-background` 동일, 헤더만 하단 `border-b`로 구분한다. 같은 높이 + 배경 농도 차이로 위계를 만드는 방식은 쓰지 않는다.

---

## 6. 컴포넌트 통합 규칙

### 6.1 메뉴바 (`src/components/layout/MenuBar.tsx`, `src/components/mame/layout/MenuBar.tsx`)

- 높이 `h-menubar`(40px), 좌우 패딩 `px-4`.
- 좌측: `Kuro` 또는 `Mame` 텍스트 라벨 한 줄 + 1줄 부제. 이모지·pill 배지 제거.
- 가운데: shadcn `Menubar` 그대로. 메뉴 트리거 `h-control px-3 rounded-control`.
- 우측: 모드 또는 작업 요약 한 개. badge 변형 1종(outline)만 허용.
- 드롭다운 separator는 shadcn 기본만. 임의 `h-px bg-gray-200` 제거.
- 모든 트리거에 `focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2` 강제 (현재 코드 0% 적용).

### 6.2 상태바

- 높이 `h-statusbar`(24px), `text-caption`, 좌우 패딩 `px-3`.
- 슬롯 셋: 좌측 메시지, 중앙 요약(서브툴별), 우측 sidecar 상태.
- 에러 표현은 한 가지로. 빨간 pill 대신 텍스트 + retry 링크.
- 상태 점은 `8px` 원형 한 종류, 색은 `--color-success/warning/error/info` 매핑. 색 단독 금지: 점 옆에 라벨 텍스트 또는 도형 차이 동반.
- ARIA: 좌측 메시지 영역에 `aria-live="polite"` 강제.
- 기존 `text-2xs`, `h-statusbar`(미정의 Tailwind 클래스), `--verdict-*`, `--status-*` 변수 제거. §4 토큰으로 일원화.

### 6.3 사이드바

- 폭 `w-sidebar`(320px). 외곽 `border + rounded-container + bg-card`. shadow 없음.
- 내부 패딩 `12px`, 섹션 gap `12px`. 카드 안에 카드를 두지 않는다(평탄화).
- 하단 액션 영역도 같은 컨테이너 안. 푸터는 `border-t` 1px로 구분만.
- 실행 버튼: Primary `h-control-primary` 1개, 보조 `h-control`. 화면당 Primary 1개 원칙을 사이드바에서도 지킴.

### 6.4 패널 카드

세 종으로만 정의한다. 이름과 책임이 다르면 같은 시각이라도 다른 컴포넌트로 분리한다.

| 종류 | 용도 | 헤더 | 본문 |
|---|---|---|---|
| `SurfacePanel` | 입력·파라미터 | `h-control`, sentence case 제목 | 폼 컨트롤 |
| `DataPanel` | 표·시퀀스 뷰어 | `h-control` + 우측 보조 액션 | 스크롤 영역, `ErrorBoundary`로 감싼다 |
| `ActionPanel` | 상태·실행 | `h-control` + 상태 뱃지 | 진행률·요약 + CTA |

공통 스펙: `border + rounded-container + bg-card`. 헤더 배경 `bg-muted/40`. 헤더 카피는 `Input files`, `Parameters`, `Design output`, `Verdict table` 같은 sentence case로 통일. `INPUT`, `PARAMETERS` 대문자 헤더 금지.

### 6.5 버튼·필드

| 계층 | 높이 | variant | 용도 |
|---|---|---|---|
| Primary | `h-control-primary` (36) | 검정 배경 | CTA, Run. 화면당 1개 |
| Secondary | `h-control` (32) | outline | 보조 액션 |
| Destructive | `h-control` (32) | `--color-error` outline | Cancel, Clear, Delete |
| Ghost / 메뉴 트리거 | `h-control` (32) | 배경 없음 | 드롭다운 트리거 |
| Icon | `32×32` | ghost | 단독 아이콘 액션 |

- 입력 필드 `h-control`. 파일 경로는 `font-mono text-caption`.
- 5상태 모두 정의: default / hover / **focus-visible** / active / disabled.
- focus-visible 통일 클래스: `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2`. 모든 인터랙티브 요소에 강제.
- transition 통일: `transition-colors duration-fast`. 색 외 속성(transform/opacity)이 필요하면 `duration-base`.

### 6.6 표

- 헤더 `h-control`, 행 `h-control` 고정. dense 모드는 `text-caption` + 패딩 축소로만 처리한다.
- 숫자 컬럼 `tabular-nums`.
- 상태 배지: outline 1종 + 의미 색(`text-success`/`text-warning`/`text-error`/`text-info`). 색 단독 금지 — 도형 prefix(●▲■◆) 또는 아이콘으로 색맹 대응.
- zebra row 사용 금지(border-only로 가독성 확보).

### 6.7 다이얼로그

- shadcn `Dialog` 그대로. 자체 카드 스타일 덧대기 금지.
- 폭 3단계로 고정:
  - 확인 다이얼로그(About, Clear Confirm): `max-w-sm`
  - 정보 다이얼로그(Help, View): `max-w-md`
  - 폼·내보내기 다이얼로그(Export, Settings): `max-w-2xl`
- 현재 `MenuBar.tsx:161`(About `max-w-sm`), `AppLayout.tsx:235`(Clear `max-w-xs`)는 위 분류에 맞춰 정정. About는 `max-w-sm` 유지, Clear는 `max-w-sm`로 통일.
- footer 정렬은 우측, Primary 1개 + Cancel.
- 키보드 트랩 강제: shadcn Dialog의 `Radix.FocusScope` 그대로 활용. ESC 닫기 보존.

### 6.8 빈/오류/로딩 상태

웹 디자인 원칙의 4상태(Loading / Empty / Error / Success)를 모든 데이터 영역에 강제한다. 텍스트 규칙만 두지 않고 컴포넌트 계약으로 박는다.

```tsx
// src/components/ui/StateView.tsx
interface StateViewProps {
  variant: 'loading' | 'empty' | 'error' | 'success';
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
}
```

규칙:

- Empty: 한 줄 제목 + 한 줄 보조 + 다음 행동 버튼 1개.
- Error: "무엇이 / 어떻게 고치는지" 두 가지를 함께. 예: "FASTA 헤더가 없습니다. `>`로 시작하는 줄을 추가하세요."
- Loading: skeleton 1종. 스피너는 sidecar 호출 중에만(별도 `Spinner` 컴포넌트, 크기 16/24px 두 종).
- 모든 `DataPanel`은 `ErrorBoundary`로 감싸 fallback에 `<StateView variant="error">` 표시.

---

## 7. 카피 규칙

- 제품명 `kuma`, 탭명 `Kuro`/`Mame`. 메뉴바·About에서 `KURO`, `mame` 혼용을 없앤다.
- 이모지·캐릭터 카피·장식 문구 금지.
- 도구 설명은 짧은 명사구 또는 명령형. 예: `Directed mutagenesis workbench`, `NB-plate verdict`, `Ready to run`, `No results yet`.
- form label은 placeholder 단독 대체 금지. label-input은 `htmlFor`/`id`로 항상 묶는다.

---

## 8. 구현 순서

| Phase | 산출물 | 검증 |
|---|---|---|
| 1. 토큰 | `index.css` 토큰 16종 + reduced-motion 미디어 쿼리, `tailwind.config.js` theme.extend 매핑, `MainShell` 계층 정리, `StateView`/`Spinner` 빈 컴포넌트 스캐폴드 | tsc 0, 새 토큰 유틸 클래스가 storybook/lint에서 인식 |
| 2. 메뉴바·상태바 | 공통 `SubtoolMenuBar`, `GlobalStatusBar`(`aria-live` 포함), focus-visible 일괄 적용 | 두 탭 메뉴/상태 높이·패딩 동일, 키보드 탭 순서 정상 |
| 3. 사이드바·패널 | `SurfacePanel`/`DataPanel`/`ActionPanel` 도입, 카드 중첩 제거, `--verdict-*`/`--status-*` 제거하고 의미 색으로 치환 | 사이드바 폭·radius·border 동일, 미정의 변수 grep 결과 0건 |
| 4. 데이터 패널·다이얼로그·빈 상태 | 표 행/badge/4상태 통일, `StateView` 실 적용, Dialog 폭 3단계 정정, `ErrorBoundary` 적용 | 스크린샷 diff 잔차 제거, 색맹 시뮬레이터(Chrome devtools)에서 상태 구분 가능 |
| 5. QA | 치수 측정·해상도 비교·`docs/screenshots` 재촬영, accessibility 자동 점검(axe) | 9장 체크리스트 전부 통과, axe critical 0건 |

---

## 9. 완료 기준

다음을 모두 만족하면 1차 통일을 닫는다.

1. 메뉴바 40, 상태바 24, 사이드바 320, 컨테이너 radius 12, 컨트롤 radius 8, 컨트롤 높이 32, Primary 36이 두 탭에서 동일하다.
2. 기본 패널에 shadow가 없다. shadow는 다이얼로그·드롭다운·토스트에만 남는다.
3. 두 탭에서 이모지·`KURO`/`mame` 대소문자 혼용·자체 pill 배지가 사라진다.
4. 토큰 16종 + Tailwind theme.extend로만 메뉴바·상태바·사이드바·패널이 구성된다. 코드 grep에서 `text-\[`, `h-\[`, `rounded-\[`, `--verdict-`, `--status-`, `text-2xs` 일치 0건.
5. Empty / Error / Loading / Success 네 상태가 `StateView` 컴포넌트 호출로 데이터 영역마다 정의된다.
6. axe-core 자동 점검에서 critical 0건, 색맹 시뮬레이터에서 모든 상태 구분 가능.

---

## 10. 보존하는 차이

다음은 손대지 않는다. 도메인이 다르기 때문이다.

- `kuro`의 3분할 메인(Sequence / Design / Plate)
- `mame`의 `SummaryRow`와 verdict 중심 흐름
- 각 탭의 메뉴 항목 수와 도메인 용어

구조는 다르되 시각 문법은 같다. 이 한 줄이 이번 작업의 전부다.
