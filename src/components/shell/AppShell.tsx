import type { DragEventHandler, ReactNode, RefObject } from "react";
import { PanelRightOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import { useLayoutStore } from "@/store/layoutStore";
import { ResizeHandle } from "./ResizeHandle";

/** Min/max sidebar width constants (spec §15.5). */
const SIDEBAR_MIN = 180;
const SIDEBAR_MAX = 480;

/** Default inspector panel width (mockup grid §2). */
const INSPECTOR_DEFAULT_WIDTH = 320;

type AppShellProps = {
  tool: "kuro" | "mame";
  titlebar: ReactNode;
  /** 옵션 brand bar. Phase D에서 도입 예정. */
  appbar?: ReactNode;
  /** mame phase tabs 등 subnav 슬롯. kuro는 미사용. */
  subnav?: ReactNode;
  /** 사이드바 슬롯. null 또는 undefined 전달 시 <aside> 미렌더. */
  sidebar?: ReactNode;
  /** 메인 워크스페이스 슬롯. */
  main: ReactNode;
  /** 하단 상태바 슬롯. */
  statusbar: ReactNode;
  /** drag/drop, keyboard 등 루트 wrapper 이벤트 위임용. */
  rootRef?: RefObject<HTMLDivElement>;
  onDragOver?: DragEventHandler;
  onDrop?: DragEventHandler;
  onDragLeave?: DragEventHandler;
  isDragOver?: boolean;
  className?: string;
  /** dialog, toast 등 absolute-positioned overlay. 형제 위치로 마운트. */
  children?: ReactNode;
  /**
   * 드래그 리사이즈 핸들 비활성화. 기본값 false.
   * mame PlateView 우측 aside 등 리사이즈 불필요한 슬롯에 사용 (spec §15.3).
   */
  disableResize?: boolean;
  /** 우측 inspector 슬롯. null/undefined 시 inspector 미렌더. */
  inspector?: ReactNode;
  /** inspector 표시 여부. 기본 true (사용자 결정: 항상 열림). */
  inspectorOpen?: boolean;
  /** inspector 토글 버튼 클릭 콜백. */
  onInspectorToggle?: () => void;
  /** inspector 고정 폭(px). 기본 320. */
  inspectorWidth?: number;
};

/**
 * AppShell
 *
 * kuro/mame 공유 레이아웃 셸.
 * titlebar / appbar / subnav / workspace(sidebar+main) / statusbar 슬롯으로 구성.
 *
 * - `data-tool` 어트리뷰트를 단독 부착 (Phase A에서 각 wrapper가 담당하던 책임 인수).
 * - sidebar가 null/undefined이면 <aside>를 렌더하지 않아 main이 전체 폭을 차지.
 * - drag/drop 이벤트는 rootRef + handler props로 wrapper에서 위임.
 */
export function AppShell({
  tool,
  titlebar,
  appbar,
  subnav,
  sidebar,
  main,
  statusbar,
  rootRef,
  isDragOver,
  className,
  children,
  disableResize = false,
  inspector,
  inspectorOpen,
  onInspectorToggle,
  inspectorWidth = INSPECTOR_DEFAULT_WIDTH,
  ...handlers
}: AppShellProps) {
  const sidebarWidth = useLayoutStore((s) => s.sidebarWidth ?? s.computedDefault);
  const setSidebarWidth = useLayoutStore((s) => s.setSidebarWidth);

  const showInspector = inspector != null && (inspectorOpen ?? true);
  const showToggle = inspector != null && (inspectorOpen ?? true) === false;

  return (
    <div
      ref={rootRef}
      data-tool={tool}
      className={cn(
        "flex h-screen flex-col bg-background",
        isDragOver && "ring-2 ring-inset ring-ring",
        className,
      )}
      {...handlers}
    >
      {/* titlebar 슬롯: MenuBar */}
      {titlebar}

      {/* appbar 슬롯: brand bar (Phase D 도입 예정) */}
      {appbar}

      {/* subnav 슬롯: phase tabs (mame) 등 */}
      {subnav}

      {/* workspace 영역 */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        {sidebar != null && (
          <aside
            data-testid="sidebar"
            data-tour={`${tool}-workflow`}
            style={{ width: sidebarWidth }}
            className="relative flex shrink-0 flex-col overflow-x-hidden border-r border-border bg-card"
          >
            {sidebar}
            {!disableResize && (
              <ResizeHandle
                width={sidebarWidth}
                min={SIDEBAR_MIN}
                max={SIDEBAR_MAX}
                onResize={setSidebarWidth}
              />
            )}
          </aside>
        )}
        <main
          data-testid="main-content"
          data-tour={`${tool}-workspace`}
          className="relative flex flex-1 min-w-0 min-h-0 flex-col overflow-hidden"
        >
          {main}
          {showToggle && (
            <button
              type="button"
              aria-label="Open inspector"
              onClick={onInspectorToggle}
              className="absolute top-2 right-3 h-6 px-2 rounded border border-border bg-card text-muted-foreground hover:bg-muted"
            >
              <PanelRightOpen className="h-3.5 w-3.5" />
            </button>
          )}
        </main>
        {showInspector && (
          <aside
            data-testid="inspector"
            data-tour={`${tool}-inspector`}
            style={{ width: inspectorWidth }}
            className="flex shrink-0 flex-col overflow-x-hidden border-l border-border bg-card"
          >
            {inspector}
          </aside>
        )}
      </div>

      {/* statusbar 슬롯 */}
      {statusbar}

      {/* overlays: dialogs, toasts */}
      {children}
    </div>
  );
}
