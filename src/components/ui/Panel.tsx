/**
 * Panel 3종 컴포넌트 — Phase 3 §6.4
 *
 * 공통 외곽: border + rounded-container + bg-card. shadow 없음.
 * 헤더: h-control, bg-muted/40, sentence case 제목, font-semibold text-title.
 * 카드 안에 카드 금지: 자식이 또 패널이면 console.warn (강제 차단 없음).
 *
 * 사용처:
 *   <SurfacePanel title="Input files">…폼 컨트롤…</SurfacePanel>
 *   <DataPanel title="Design output" headerSlot={<button>…</button>}>…표…</DataPanel>
 *   <ActionPanel title="Run" statusBadge={<Badge>Ready</Badge>}>…CTA…</ActionPanel>
 */
import { type ReactNode, Children, isValidElement } from "react";
import { cn } from "@/lib/utils";
import { ErrorBoundary } from "./ErrorBoundary";
import { StateView } from "./StateView";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface PanelBaseProps {
  title: string;
  /** 헤더 보조 한 줄 (text-caption text-muted-foreground) */
  description?: string;
  /** 헤더 우측 보조 액션 슬롯 */
  headerSlot?: ReactNode;
  className?: string;
  children: ReactNode;
}

// ---------------------------------------------------------------------------
// Dev-only nested panel warning
// ---------------------------------------------------------------------------

const PANEL_DISPLAY_NAMES = new Set(["SurfacePanel", "DataPanel", "ActionPanel"]);

function warnNestedPanel(children: ReactNode): void {
  if (process.env.NODE_ENV !== "production") {
    Children.forEach(children, (child) => {
      if (
        isValidElement(child) &&
        typeof child.type === "function" &&
        PANEL_DISPLAY_NAMES.has((child.type as { displayName?: string }).displayName ?? "")
      ) {
        console.warn(
          "[Panel] 카드 안에 카드 중첩 감지됨. 패널은 서로 nest하지 않는다 (§6.4).",
        );
      }
    });
  }
}

// ---------------------------------------------------------------------------
// Shared sub-components
// ---------------------------------------------------------------------------

interface PanelHeaderProps {
  title: string;
  description?: string;
  left?: ReactNode;
  right?: ReactNode;
}

function PanelHeader({ title, description, left, right }: PanelHeaderProps) {
  return (
    <header className="flex h-control shrink-0 items-center gap-2 border-b border-border bg-muted/40 px-3">
      {left && <span className="flex-shrink-0">{left}</span>}
      <div className="flex min-w-0 flex-1 flex-col justify-center">
        <span className="truncate text-title font-semibold leading-none text-foreground">
          {title}
        </span>
        {description && (
          <span className="mt-0.5 truncate text-caption text-muted-foreground leading-none">
            {description}
          </span>
        )}
      </div>
      {right && <span className="flex-shrink-0">{right}</span>}
    </header>
  );
}

// ---------------------------------------------------------------------------
// SurfacePanel — 입력·파라미터
// ---------------------------------------------------------------------------

export function SurfacePanel({
  title,
  description,
  headerSlot,
  className,
  children,
}: PanelBaseProps) {
  warnNestedPanel(children);
  return (
    <section
      className={cn(
        "flex min-h-0 flex-col overflow-hidden rounded-container border border-border bg-card",
        className,
      )}
    >
      <PanelHeader title={title} description={description} right={headerSlot} />
      <div className="min-h-0 flex-1 overflow-auto p-3">{children}</div>
    </section>
  );
}
SurfacePanel.displayName = "SurfacePanel";

// ---------------------------------------------------------------------------
// DataPanel — 표·시퀀스 뷰어. 내부 ErrorBoundary 자동 적용.
// ---------------------------------------------------------------------------

export interface DataPanelProps extends PanelBaseProps {
  onError?: (e: Error) => void;
}

export function DataPanel({
  title,
  description,
  headerSlot,
  className,
  children,
  onError: _onError,
}: DataPanelProps) {
  warnNestedPanel(children);

  const fallback = (
    <div className="flex flex-1 items-center justify-center p-4">
      <StateView
        variant="error"
        title="표시할 수 없습니다"
        description="컴포넌트 렌더링 중 오류가 발생했습니다."
      />
    </div>
  );

  return (
    <section
      className={cn(
        "flex min-h-0 flex-col overflow-hidden rounded-container border border-border bg-card",
        className,
      )}
    >
      <PanelHeader title={title} description={description} right={headerSlot} />
      <div className="min-h-0 flex-1 overflow-hidden">
        <ErrorBoundary fallback={fallback}>{children}</ErrorBoundary>
      </div>
    </section>
  );
}
DataPanel.displayName = "DataPanel";

// ---------------------------------------------------------------------------
// ActionPanel — 상태·실행. 헤더 좌측 statusBadge 슬롯.
// ---------------------------------------------------------------------------

export interface ActionPanelProps extends PanelBaseProps {
  /** 헤더 좌측 상태 배지 */
  statusBadge?: ReactNode;
}

export function ActionPanel({
  title,
  description,
  headerSlot,
  statusBadge,
  className,
  children,
}: ActionPanelProps) {
  warnNestedPanel(children);
  return (
    <section
      className={cn(
        "flex min-h-0 flex-col overflow-hidden rounded-container border border-border bg-card",
        className,
      )}
    >
      <PanelHeader
        title={title}
        description={description}
        left={statusBadge}
        right={headerSlot}
      />
      <div className="min-h-0 flex-1 overflow-auto p-3">{children}</div>
    </section>
  );
}
ActionPanel.displayName = "ActionPanel";
