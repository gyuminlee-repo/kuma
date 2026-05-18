/**
 * MajorSubnav — horizontal major-step nav for Phase F layout.
 *
 * [source: spec Phase F — F4 shadcn TabsList 통일]
 *
 * Props:
 *   majors: array of { id, labelKey, countBadge? }
 *
 * Layout: outer flex row (border-b) contains:
 *   - <Tabs> + <TabsList> (shadcn) for tab switching
 *
 * Accessibility: Radix Tabs primitives provide role=tablist / role=tab /
 *   aria-selected natively.
 *
 * Note: Clear All entry-point moved to MenuBar → Edit menu (+ Cmd/Ctrl+Shift+R
 *   shortcut routes through shared ClearConfirmDialog in AppLayout). See
 *   `src/components/dialogs/ClearConfirmDialog.tsx`.
 */

import { useTranslation } from "react-i18next";
import { useAppStore } from "@/store/appStore";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { MajorStepId } from "@/store/slices/navigationSlice";

export interface MajorNavItem {
  id: MajorStepId;
  labelKey: string;
  /** v1: always undefined (§14 count badge criteria未定). Rendered only when provided. */
  countBadge?: number;
}

interface MajorSubnavProps {
  majors: MajorNavItem[];
}

export function MajorSubnav({ majors }: MajorSubnavProps) {
  const { t } = useTranslation();
  const currentMajor = useAppStore((s) => s.currentMajor);
  const setMajor = useAppStore((s) => s.setMajor);

  return (
    <div className="flex items-center border-b border-border px-3 pt-2 pb-0">
      <Tabs
        value={currentMajor}
        onValueChange={(v) => setMajor(v as MajorStepId)}
      >
        <TabsList className="shrink-0 mx-3 mt-2 w-fit">
          {majors.map((m) => (
            <TabsTrigger
              key={m.id}
              value={m.id}
              data-major-tab={m.id}
            >
              <span>{t(m.labelKey)}</span>
              {m.countBadge !== undefined && (
                <span
                  className="inline-flex items-center justify-center h-4 min-w-[1rem] rounded-full bg-muted text-muted-foreground text-xs px-1"
                  aria-label={String(m.countBadge)}
                >
                  {m.countBadge}
                </span>
              )}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
    </div>
  );
}
