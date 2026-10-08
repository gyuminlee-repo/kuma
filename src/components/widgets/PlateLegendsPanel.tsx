import { Card, CardContent } from "@/components/ui/card";
import { useTranslation } from "react-i18next";
import {
  PLATE_FILL_DEST_COMPLETE,
  PLATE_FILL_DEST_PARTIAL,
  PLATE_FILL_FORWARD,
  PLATE_FILL_REVERSE,
} from "@/lib/platePreviewStyles";

export function PlateLegendsPanel() {
  const { t } = useTranslation();
  // DestPlateView only ever draws two states for a filled well (complete,
  // partial), not three: legendDest used to name a third shade that nothing
  // rendered, and legendDestPartial's swatch (emerald-200) did not match the
  // amber DestPlateView actually uses for a partial well.
  // Swatch classes come from the same constants the cells use, so the dark
  // variants cannot go missing here again (the swatches were light-only
  // while the cells shifted to dark:bg-*-500).
  const items: Array<{ cls: string; key: string }> = [
    { cls: PLATE_FILL_FORWARD, key: "exportPreview.legendForward" },
    { cls: PLATE_FILL_REVERSE, key: "exportPreview.legendReverse" },
    { cls: PLATE_FILL_DEST_COMPLETE, key: "exportPreview.legendDestMerged" },
    { cls: PLATE_FILL_DEST_PARTIAL, key: "exportPreview.legendDestPartial" },
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
