import type { ReactNode } from "react";

export interface SubtoolMenuBarProps {
  /** 서브툴 이름. 메뉴바 좌측 라벨로 표시된다. */
  label: "Kuro" | "Mame";
  /** 부제 텍스트. 라벨 아래 작은 글씨로 표시된다. */
  subtitle: string;
  /**
   * shadcn Menubar 또는 DropdownMenu 등 메뉴 트리거 모음.
   * 트리거 권장 클래스:
   * `h-control px-3 rounded-control hover:bg-accent focus-visible:outline-none
   *  focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2
   *  transition-colors duration-fast`
   */
  menus: ReactNode;
  /**
   * 우측 슬롯. 모드 또는 작업 요약 배지 1개.
   * outline badge 변형 1종만 허용. 생략 가능.
   */
  rightSlot?: ReactNode;
}

/**
 * SubtoolMenuBar
 *
 * kuro/mame 양쪽에서 공유하는 서브툴 메뉴바 셸.
 * 높이 `h-menubar`(40px), 패딩 `px-4`.
 * 브랜드 배지·이모지·대문자 로고를 포함하지 않는다.
 *
 * 계획서 §6.1 준수.
 */
export function SubtoolMenuBar({
  label,
  subtitle,
  menus,
  rightSlot,
}: SubtoolMenuBarProps) {
  return (
    <div
      className="px-4 py-2 flex flex-col gap-2 bg-background border-b border-border dark:bg-background dark:border-border"
      role="navigation"
      aria-label={`${label} menu bar`}
    >
      {/* 1행: 라벨 + 부제 (좌) · 우측 슬롯 */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex flex-col leading-tight select-none">
          <span className="text-title font-semibold text-foreground">{label}</span>
          <span className="text-caption text-muted-foreground">{subtitle}</span>
        </div>
        {rightSlot && <div className="flex items-center">{rightSlot}</div>}
      </div>

      {/* 2행: 메뉴 트리거 */}
      <div className="flex items-center gap-0.5">{menus}</div>
    </div>
  );
}
