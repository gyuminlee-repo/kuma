# Echo/Janus Export Plate Preview 구현 계획

**목표:** KURO Export 탭 메인 최상단에 Echo 384-well + Janus 96-well plate 시각화 추가, Design Report 기존 미리보기 제거

**아키텍처:** 기존 dry-run RPC 응답을 어댑터로 변환해 plate 그리드에 렌더. EchoPlateView(384 신규), JanusPlateView(96 2-rack 신규), ExportPlatePreview(컨테이너)로 분리. 백엔드 무변경.

**기술 스택:** React 19 + TypeScript, shadcn Tabs/Card, lucide-react, Vitest

**근거 문서:** [source: docs/design/2026-05-18-echo-janus-export-preview-help-icons.md]

---

## 파일 구조

### 생성
| 파일 | 책임 |
|---|---|
| `src/components/widgets/EchoPlateView.tsx` | 384-well grid (16x24), fwd/rev row stripe, hover tooltip |
| `src/components/widgets/JanusPlateView.tsx` | 96-well grid 2개 (Rack 1 fwd + Rack 2 dest) 좌우 배치 |
| `src/components/widgets/ExportPlatePreview.tsx` | 컨테이너, ToggleGroup (Echo / JANUS 단일 선택), 자동 RPC 호출, loading/error/empty state |
| `src/lib/echoJanusAdapter.ts` | dry-run row → plate cell 타입 변환 |
| `src/components/widgets/EchoPlateView.test.tsx` | 384 grid 렌더, fwd/rev stripe, well 좌표 |
| `src/components/widgets/JanusPlateView.test.tsx` | 2 rack 배치, well 좌표 |
| `src/components/widgets/ExportPlatePreview.test.tsx` | mount RPC 호출, empty/error state |
| `src/lib/echoJanusAdapter.test.ts` | row → cell 변환 단위 |

### 수정
| 파일 | 변경 |
|---|---|
| `src/components/steps/ExportStepView.tsx:33-36` | `<div className="space-y-6">` 최상단에 `<ExportPlatePreview />` 삽입 |
| `src/components/dialogs/DesignReportContent.tsx:405-486` | Echo/Janus 섹션 + state echoPreview/janusPreview (L89-91) + RPC 호출(L101-104) 제거. 관련 import 정리 |

### 변경 없음
- `python-core/sidecar_kuro/handlers/export.py` (dry-run handler)
- `python-core/sidecar_kuro/dispatcher.py`
- `src/components/inspectors/kuro/ExportInspector.tsx`

---

## 핵심 타입 (adapter)

```typescript
// src/lib/echoJanusAdapter.ts
export interface EchoCell {
  well: string;             // "A01", "P24"
  rowLetter: string;        // "A".."P"
  colNumber: number;        // 1..24
  isFwd: boolean;           // odd row (A,C,E,G,I,K,M,O)
  sourceWellName: string;
  destPlate: string;
  destWell: string;         // "A1".."H12"
  transferVolNl: number;
}

export interface JanusCell {
  well: string;             // "A1".."H12"
  rowLetter: string;
  colNumber: number;
  rack: 1 | 2;
  name: string;
  volumeUl: number;
}

export function adaptEchoRows(rows: EchoDryRunRow[]): EchoCell[];
export function adaptJanusRows(rows: JanusDryRunRow[]): { rack1: JanusCell[]; rack2: JanusCell[] };
```

---

## Task 1: echoJanusAdapter (TDD)

**파일:** 생성 `src/lib/echoJanusAdapter.ts`, `src/lib/echoJanusAdapter.test.ts`

- [ ] **Step 1-1: 실패 테스트 작성**

```typescript
import { describe, it, expect } from "vitest";
import { adaptEchoRows, adaptJanusRows } from "./echoJanusAdapter";

describe("adaptEchoRows", () => {
  it("parses 384-well coord A01 row=A col=1 isFwd=true", () => {
    const cells = adaptEchoRows([{
      source_plate: "Source [1]", source_well_name: "P1-fw",
      source_well: "A01", dest_plate: "Dest [1]",
      dest_well_name: "P1", dest_well: "A1", transfer_vol: 100,
    }]);
    expect(cells[0]).toMatchObject({
      well: "A01", rowLetter: "A", colNumber: 1, isFwd: true,
    });
  });
  it("rev row B even = isFwd=false", () => {
    const cells = adaptEchoRows([{ source_well: "B03", source_well_name: "x", source_plate: "", dest_plate: "", dest_well_name: "", dest_well: "", transfer_vol: 50 }]);
    expect(cells[0].isFwd).toBe(false);
  });
});

describe("adaptJanusRows", () => {
  it("splits rack 1 (fwd) and rack 2 (dest)", () => {
    const { rack1, rack2 } = adaptJanusRows([
      { name: "P1-fw", type: "primer", dsp_rack_label: "x", no: 1, asp_rack: 1, asp_posi: "A1", dsp_rack: 2, dsp_posi: "A1", volume: 2.0 },
      { name: "P1-rv", type: "primer", dsp_rack_label: "x", no: 2, asp_rack: 1, asp_posi: "A2", dsp_rack: 2, dsp_posi: "A1", volume: 2.0 },
    ]);
    expect(rack1).toHaveLength(2);
    expect(rack2).toHaveLength(2);
    expect(rack1[0]).toMatchObject({ rack: 1, well: "A1" });
  });
});
```

- [ ] **Step 1-2: 실패 확인**: `npx vitest run src/lib/echoJanusAdapter.test.ts` 결과 FAIL
- [ ] **Step 1-3: 구현** (adapter.ts) 위 인터페이스 + 384 row 짝/홀 판정 + janus rack split
- [ ] **Step 1-4: 통과 확인**: `npx vitest run src/lib/echoJanusAdapter.test.ts` 결과 PASS
- [ ] **Step 1-5: 커밋**: `git add src/lib/echoJanus* && git commit -m "vX: add echoJanusAdapter"`

---

## Task 2: EchoPlateView (384-well)

**파일:** 생성 `src/components/widgets/EchoPlateView.tsx`, `EchoPlateView.test.tsx`

- [ ] **Step 2-1: 실패 테스트**

```tsx
import { render, screen } from "@testing-library/react";
import { EchoPlateView } from "./EchoPlateView";

it("renders 16 rows x 24 cols (384 cells)", () => {
  const { container } = render(<EchoPlateView cells={[]} />);
  expect(container.querySelectorAll("[data-testid='echo-cell']")).toHaveLength(384);
});
it("applies fwd stripe to odd rows", () => {
  const { container } = render(<EchoPlateView cells={[]} />);
  const rowA = container.querySelector("[data-row='A']");
  expect(rowA?.className).toMatch(/fwd|blue/);
});
it("renders cell tooltip for filled well A01", () => {
  render(<EchoPlateView cells={[{ well: "A01", rowLetter: "A", colNumber: 1, isFwd: true, sourceWellName: "P1-fw", destPlate: "D1", destWell: "A1", transferVolNl: 100 }]} />);
  expect(screen.getByTitle(/P1-fw/)).toBeInTheDocument();
});
```

- [ ] **Step 2-2: 실패 확인**
- [ ] **Step 2-3: 구현**

```tsx
// EchoPlateView.tsx
import { cn } from "@/lib/utils";
import type { EchoCell } from "@/lib/echoJanusAdapter";

const ROWS = ["A","B","C","D","E","F","G","H","I","J","K","L","M","N","O","P"] as const;
const COLS = Array.from({ length: 24 }, (_, i) => i + 1);

interface Props { cells: EchoCell[]; className?: string }

export function EchoPlateView({ cells, className }: Props) {
  const byWell = new Map(cells.map(c => [c.well, c]));
  return (
    <div className={cn("min-w-[700px] overflow-x-auto", className)}>
      <div className="grid grid-cols-[auto_repeat(24,1fr)] gap-px">
        <div />
        {COLS.map(c => <div key={c} className="text-caption text-center text-muted-foreground">{c}</div>)}
        {ROWS.map((r, idx) => {
          const isFwdRow = idx % 2 === 0;
          return (
            <>
              <div key={`label-${r}`} className="text-caption text-muted-foreground text-right pr-1">{r}</div>
              {COLS.map(c => {
                const well = `${r}${String(c).padStart(2,"0")}`;
                const cell = byWell.get(well);
                const tip = cell ? `${cell.sourceWellName} → ${cell.destPlate} ${cell.destWell} (${cell.transferVolNl} nL)` : well;
                return (
                  <div
                    key={well}
                    data-testid="echo-cell"
                    data-row={r}
                    title={tip}
                    className={cn(
                      "aspect-square rounded-[2px] border border-border/50",
                      isFwdRow ? "bg-blue-50 dark:bg-blue-950/30" : "bg-orange-50 dark:bg-orange-950/30",
                      cell && (isFwdRow ? "bg-blue-400" : "bg-orange-400")
                    )}
                  />
                );
              })}
            </>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 2-4: 통과 확인**
- [ ] **Step 2-5: 커밋**

---

## Task 3: JanusPlateView (96-well x 2 rack)

**파일:** 생성 `JanusPlateView.tsx`, `JanusPlateView.test.tsx`

- [ ] **Step 3-1: 실패 테스트** (rack 좌우 배치, 96 셀 × 2 = 192, hover tooltip)
- [ ] **Step 3-2: 실패 확인**
- [ ] **Step 3-3: 구현** Step 2 패턴 응용, ROWS A-H × COLS 1-12, rack 1·2 side-by-side
- [ ] **Step 3-4: 통과 확인**
- [ ] **Step 3-5: 커밋**

---

## Task 4: ExportPlatePreview 컨테이너

**파일:** 생성 `ExportPlatePreview.tsx`, `ExportPlatePreview.test.tsx`

- [ ] **Step 4-1: 실패 테스트**

```tsx
import { vi } from "vitest";
import { invoke } from "@tauri-apps/api/core";
vi.mock("@tauri-apps/api/core", () => ({ invoke: vi.fn() }));

it("calls echo + janus dry-run on mount", async () => {
  (invoke as any).mockResolvedValue([]);
  render(<ExportPlatePreview />);
  await waitFor(() => {
    expect(invoke).toHaveBeenCalledWith("export_echo_mapping_dry_run", expect.anything());
    expect(invoke).toHaveBeenCalledWith("export_janus_mapping_dry_run", expect.anything());
  });
});

it("shows empty state when no rows", async () => {
  (invoke as any).mockResolvedValue([]);
  render(<ExportPlatePreview />);
  expect(await screen.findByText(/no.*mapping/i)).toBeInTheDocument();
});

it("shows error with retry on failure", async () => {
  (invoke as any).mockRejectedValue(new Error("boom"));
  render(<ExportPlatePreview />);
  expect(await screen.findByText(/boom/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /retry|재시도/i })).toBeInTheDocument();
});
```

- [ ] **Step 4-2: 실패 확인**
- [ ] **Step 4-3: 구현**

```tsx
// ExportPlatePreview.tsx
import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Button } from "@/components/ui/button";
import { useTranslation } from "react-i18next";
import { adaptEchoRows, adaptJanusRows } from "@/lib/echoJanusAdapter";
import { EchoPlateView } from "./EchoPlateView";
import { JanusPlateView } from "./JanusPlateView";

export function ExportPlatePreview() {
  const { t } = useTranslation();
  const [view, setView] = useState<"echo" | "janus">("echo");
  const [echo, setEcho] = useState<ReturnType<typeof adaptEchoRows>>([]);
  const [janus, setJanus] = useState<ReturnType<typeof adaptJanusRows>>({ rack1: [], rack2: [] });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true); setError(null);
    try {
      const [e, j] = await Promise.all([
        invoke<any[]>("export_echo_mapping_dry_run", {}),
        invoke<any[]>("export_janus_mapping_dry_run", {}),
      ]);
      setEcho(adaptEchoRows(e));
      setJanus(adaptJanusRows(j));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => { void load(); }, []);

  if (error) return (
    <Card><CardContent className="p-4">
      <p className="text-error">{error}</p>
      <Button size="sm" variant="outline" onClick={load} className="mt-2">{t("common.retry")}</Button>
    </CardContent></Card>
  );
  if (loading) return <Card><CardContent className="p-4 text-muted-foreground">{t("exportPreview.loading")}</CardContent></Card>;
  if (echo.length === 0 && janus.rack1.length === 0)
    return <Card><CardContent className="p-4 text-muted-foreground">{t("exportPreview.empty")}</CardContent></Card>;

  return (
    <Card>
      <CardHeader><CardTitle>{t("exportPreview.title")}</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <ToggleGroup
          type="single"
          value={view}
          onValueChange={(v) => v && setView(v as "echo" | "janus")}
          variant="outline"
          size="sm"
        >
          <ToggleGroupItem value="echo">{t("exportPreview.echoTab")}</ToggleGroupItem>
          <ToggleGroupItem value="janus">{t("exportPreview.janusTab")}</ToggleGroupItem>
        </ToggleGroup>
        {view === "echo" && <EchoPlateView cells={echo} />}
        {view === "janus" && <JanusPlateView rack1={janus.rack1} rack2={janus.rack2} />}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 4-4: 통과 확인**
- [ ] **Step 4-5: i18n 키 추가** (en.json + ko.json)

```json
"exportPreview": {
  "title": "Mapping Preview" / "매핑 미리보기",
  "loading": "Loading preview..." / "미리보기 로딩 중...",
  "empty": "No mapping to preview. Design primers first." / "미리보기 없음. 먼저 프라이머를 디자인하세요.",
  "echoTab": "Echo 525 (384-well)",
  "janusTab": "JANUS (96-well x 2)"
}
```
`common.retry` 없으면 추가.

- [ ] **Step 4-6: 커밋**

---

## Task 5: ExportStepView 통합

**파일:** 수정 `src/components/steps/ExportStepView.tsx:33-36`

- [ ] **Step 5-1: import 추가**: `import { ExportPlatePreview } from "@/components/widgets/ExportPlatePreview";`
- [ ] **Step 5-2: JSX 삽입**

```tsx
// 변경 전
<div className="space-y-6">
  <ExportFormatSelector ... />
  <OrderSummary ... />
</div>

// 변경 후
<div className="space-y-6">
  <ExportPlatePreview />
  <ExportFormatSelector ... />
  <OrderSummary ... />
</div>
```

- [ ] **Step 5-3: typecheck**: `npx tsc --noEmit` 0 errors
- [ ] **Step 5-4: 커밋**

---

## Task 6: DesignReportContent에서 Echo/Janus 제거

**파일:** 수정 `src/components/dialogs/DesignReportContent.tsx`

- [ ] **Step 6-1: 제거 대상 라인 확인** (현재 L89-91 state, L101-104 RPC 호출, L405-486 JSX)
- [ ] **Step 6-2: state, useEffect, JSX 블록 모두 제거**. 사용하지 않게 된 import 정리.
- [ ] **Step 6-3: typecheck** 0 errors
- [ ] **Step 6-4: 스냅샷 test 있다면 갱신**: `npx vitest run -u src/components/dialogs/DesignReportContent.test`
- [ ] **Step 6-5: 커밋**

---

## Task 7: 통합 검증

- [ ] `npx tsc --noEmit` 0 errors
- [ ] `cd src-tauri && cargo check` 0 errors (백엔드 무변경, 통과 예상)
- [ ] `node scripts/i18n-parity.mjs` 통과 (en+ko 키 추가가 다른 8 언어 fallback 깨지 않는지)
- [ ] `node scripts/i18n-lint.mjs` 통과 (한글 하드코딩 0)
- [ ] `npx vitest run src/lib/echoJanus* src/components/widgets/EchoPlate* src/components/widgets/JanusPlate* src/components/widgets/ExportPlatePreview*` 모두 PASS
- [ ] `git diff --stat` 예상 파일 7개 + 테스트 4 = 11

---

## 검증 기준 (karpathy-guidelines)

- **가정 명시**: Echo source는 384, dest는 96. Janus는 96 x 2 rack. dry-run RPC 응답 형식은 `python-core/sidecar_kuro/handlers/export.py:605-720` 기준.
- **최소 코드**: 384 grid는 단순 CSS grid + map. 별도 라이브러리 미사용.
- **변경 범위 제한**: 백엔드 무변경, dry-run RPC 재사용. ExportInspector도 무변경.
- **검증 기준**: 위 Task 7 모든 항목 PASS.

---

## Risks 점검

- 384 grid가 좁은 화면(< 700px)에서 가로 스크롤 발생: `min-w-[700px] overflow-x-auto`로 처리. 추후 zoom 기능 follow-up.
- Design Report 사용자가 미리보기 사라진 것에 당황 가능: 변경 사항 release note 또는 toast 안내 follow-up.
- i18n 키 8개 다른 언어 fallback: parity 스크립트가 missing key를 빈 문자열로 채우는지 키 자체 노출하는지 확인 필요. 필요 시 8 언어에도 영문 그대로 복사.

## Confidence Check

| 축 | 점수 | 비고 |
|---|---|---|
| Completeness | 5/5 | spec 모든 요구사항 매핑 |
| Clarity | 5/5 | 파일 경로·라인·코드 블록·예상 출력 명시 |
| Feasibility | 4/5 | dry-run RPC, React, shadcn 모두 검증된 기술. Tauri invoke mock 패턴 사전 확인 안 함 (-1) |

총 14/15. 기준 12/15 초과, 진행 가능.
