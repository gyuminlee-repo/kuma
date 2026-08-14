import { Card, CardContent } from "@/components/ui/card";
import { useTranslation } from "react-i18next";

export function PlateLegendsPanel() {
  const { t } = useTranslation();
  // DestPlateView only ever draws two states for a filled well (complete,
  // partial), not three: legendDest used to name a third shade that nothing
  // rendered, and legendDestPartial's swatch (emerald-200) did not match the
  // amber DestPlateView actually uses for a partial well.
  const items: Array<{ cls: string; key: string }> = [
    { cls: "bg-blue-400", key: "exportPreview.legendForward" },
    { cls: "bg-orange-400", key: "exportPreview.legendReverse" },
    { cls: "bg-emerald-400", key: "exportPreview.legendDestMerged" },
    { cls: "bg-amber-400", key: "exportPreview.legendDestPartial" },
  ];
  return (
    <Card>
      <CardContent className="p-3 space-y-2">
        <div className="text-caption font-semibold text-muted-foreground">
          {t("exportPreview.legend")}
        </div>
        <div className="flex flex-wrap gap-3">
          {items.map((it) => (
            <div key={it.key} className="flex items-center gap-2">
              <div className={`w-5 h-3 rounded-sm border border-border/50 ${it.cls}`} />
              <span className="text-sm">{t(it.key)}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
