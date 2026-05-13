/**
 * KeyboardShortcutsDialog — 독립 단축키 안내 다이얼로그.
 * 데이터는 src/lib/shortcuts.ts SHORTCUTS 가 단일 출처.
 */
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "../ui/dialog";
import { Button } from "../ui/button";
import {
  getShortcutsFor,
  groupByCategory,
  type ShortcutCategory,
  type ShortcutEntry,
} from "../../lib/shortcuts";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  scope?: "kuro" | "mame";
}

const CATEGORY_ORDER: ShortcutCategory[] = ["file", "edit", "view", "run", "help"];

export function KeyboardShortcutsDialog({ open, onOpenChange, scope = "kuro" }: Props) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");

  const filtered = useMemo<ShortcutEntry[]>(() => {
    const entries = getShortcutsFor(scope);
    const q = query.trim().toLowerCase();
    if (!q) return entries;
    return entries.filter(
      (e) =>
        e.keys.toLowerCase().includes(q) || e.action.toLowerCase().includes(q),
    );
  }, [scope, query]);

  const groups = useMemo(() => groupByCategory(filtered), [filtered]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("shortcutsDialog.title")}</DialogTitle>
        </DialogHeader>

        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("shortcutsDialog.searchPlaceholder")}
          aria-label={t("shortcutsDialog.searchPlaceholder")}
          className="w-full rounded-md border border-border bg-background px-3 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />

        <div className="flex flex-col gap-3">
          {CATEGORY_ORDER.map((cat) => {
            const items = groups[cat];
            if (items.length === 0) return null;
            return (
              <section key={cat} aria-labelledby={`sc-${cat}`}>
                <p
                  id={`sc-${cat}`}
                  className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground"
                >
                  {t(`shortcutsDialog.category.${cat}`)}
                </p>
                <table className="w-full text-xs border-collapse">
                  <tbody>
                    {items.map((s) => (
                      <tr
                        key={s.keys + s.action}
                        className="border-b border-border/40 last:border-0"
                      >
                        <td className="py-1 pr-3 font-mono text-foreground w-1/3">
                          {s.keys}
                        </td>
                        <td className="py-1 text-muted-foreground">{s.action}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            );
          })}
          {filtered.length === 0 && (
            <p className="text-sm text-muted-foreground">
              {t("shortcutsDialog.empty")}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button size="sm" onClick={() => onOpenChange(false)}>
            {t("common.close")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
