/**
 * GlobalAppBar — 앱 최상단 고정 앱바
 *
 * 레이아웃:
 *   [KUMA 로고]   [Kuro] [Mame]   [Settings 아이콘] [LocaleToggle]
 *
 * - 탭 전환은 Radix Tabs primitive 를 쓰지 않고 일반 버튼으로 구현.
 *   active 상태는 aria-selected + data-selected 로 표현.
 * - 키보드: 좌우 화살표로 Kuro/Mame 간 이동, Home/End 지원.
 */
import { useRef, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { Settings } from "lucide-react";
import { Button } from "@/components/ui/button";
import { LocaleToggle } from "@/components/ui/LocaleToggle";

export type AppTab = "kuro" | "mame" | "evolvepro";

const TABS: { value: AppTab; label: string }[] = [
  { value: "kuro", label: "Kuro" },
  { value: "mame", label: "Mame" },
  { value: "evolvepro", label: "EVOLVEpro" },
];

export interface GlobalAppBarProps {
  activeTab: AppTab;
  onTabChange: (v: AppTab) => void;
  onOpenSettings: () => void;
}

export function GlobalAppBar({ activeTab, onTabChange, onOpenSettings }: GlobalAppBarProps) {
  const { t } = useTranslation();
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  function handleKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    const idx = TABS.findIndex((t) => t.value === activeTab);
    if (e.key === "ArrowRight" || e.key === "ArrowDown") {
      e.preventDefault();
      const next = (idx + 1) % TABS.length;
      tabRefs.current[next]?.focus();
      onTabChange(TABS[next].value);
    } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
      e.preventDefault();
      const prev = (idx - 1 + TABS.length) % TABS.length;
      tabRefs.current[prev]?.focus();
      onTabChange(TABS[prev].value);
    } else if (e.key === "Home") {
      e.preventDefault();
      tabRefs.current[0]?.focus();
      onTabChange(TABS[0].value);
    } else if (e.key === "End") {
      e.preventDefault();
      const last = TABS.length - 1;
      tabRefs.current[last]?.focus();
      onTabChange(TABS[last].value);
    }
  }

  return (
    <header
      className="h-12 shrink-0 flex items-center border-b bg-background px-4 gap-4"
      aria-label={t("globalAppBar.navAriaLabel")}
    >
      {/* 좌측: 브랜드 로고 */}
      <span className="shrink-0 text-lg font-semibold tracking-tight text-foreground select-none">
        KUMA
      </span>

      {/* 중앙: 탭 네비게이션 */}
      <nav
        role="tablist"
        aria-label={t("globalAppBar.tabsAriaLabel")}
        className="flex items-center gap-1"
        onKeyDown={handleKeyDown}
      >
        {TABS.map((tab, i) => {
          const isSelected = activeTab === tab.value;
          return (
            <button
              key={tab.value}
              ref={(el) => { tabRefs.current[i] = el; }}
              type="button"
              role="tab"
              aria-selected={isSelected}
              tabIndex={isSelected ? 0 : -1}
              className={[
                "min-w-20 h-8 px-4 rounded-lg text-sm font-medium transition-colors duration-fast",
                "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
                isSelected
                  ? "bg-accent text-foreground shadow-sm"
                  : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
              ].join(" ")}
              onClick={() => onTabChange(tab.value)}
            >
              {tab.label}
            </button>
          );
        })}
      </nav>

      {/* 우측: 설정 + 언어 (flex-1 으로 밀어냄) */}
      <div className="flex flex-1 items-center justify-end gap-1">
        <Button
          variant="ghost"
          size="sm"
          className="h-8 w-8 p-0 text-foreground/70 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
          onClick={onOpenSettings}
          aria-label={t("globalAppBar.openSettingsAriaLabel")}
          title={t("globalAppBar.openSettingsTitle")}
        >
          <Settings size={16} aria-hidden="true" />
        </Button>
        <LocaleToggle variant="icon-label" />
      </div>
    </header>
  );
}
