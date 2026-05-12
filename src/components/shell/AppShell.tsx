import type { DragEventHandler, ReactNode, RefObject } from "react";
import { cn } from "@/lib/utils";

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
  ...handlers
}: AppShellProps) {
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
            className="flex shrink-0 flex-col border-r border-border bg-card"
          >
            {sidebar}
          </aside>
        )}
        <main
          data-testid="main-content"
          className="flex flex-1 min-w-0 min-h-0 flex-col overflow-hidden"
        >
          {main}
        </main>
      </div>

      {/* statusbar 슬롯 */}
      {statusbar}

      {/* overlays: dialogs, toasts */}
      {children}
    </div>
  );
}
