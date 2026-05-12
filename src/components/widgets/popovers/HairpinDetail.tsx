import { useTranslation } from "react-i18next";
import { useFocusTrap } from "../../../hooks/useFocusTrap";
import type { SdmPrimerResult } from "../../../types/models";

export function HairpinDetail({
  result,
  onClose,
}: {
  result: SdmPrimerResult;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const focusTrapRef = useFocusTrap<HTMLDivElement>();

  const rows = [
    { label: t("hairpinDetail.rowHairpinFwd"), tm: result.hairpin_tm_fwd ?? 0, dg: result.hairpin_dg_fwd ?? 0 },
    { label: t("hairpinDetail.rowHairpinRev"), tm: result.hairpin_tm_rev ?? 0, dg: result.hairpin_dg_rev ?? 0 },
    { label: t("hairpinDetail.rowHomodimerFwd"), tm: result.homodimer_tm_fwd ?? 0, dg: result.homodimer_dg_fwd ?? 0 },
    { label: t("hairpinDetail.rowHomodimerRev"), tm: result.homodimer_tm_rev ?? 0, dg: result.homodimer_dg_rev ?? 0 },
  ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 backdrop-blur-[2px]"
      onClick={onClose}
      onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}
    >
      <div
        ref={focusTrapRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="hairpin-detail-title"
        className="min-w-80 rounded-container border border-border bg-card p-5 shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h3 id="hairpin-detail-title" className="text-lg font-semibold text-foreground">
            {t("hairpinDetail.title", { mutation: result.mutation })}
          </h3>
          <button
            onClick={onClose}
            className="px-2 text-lg text-muted-foreground hover:text-foreground"
            aria-label={t("hairpinDetail.closeAriaLabel")}
          >
            ×
          </button>
        </div>

        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="bg-muted text-muted-foreground font-semibold">
              <th className="px-3 py-1.5 text-left">{t("hairpinDetail.colType")}</th>
              <th className="px-3 py-1.5 text-right">{t("hairpinDetail.colTm")}</th>
              <th className="px-3 py-1.5 text-right">{t("hairpinDetail.colDg")}</th>
              <th className="px-3 py-1.5 text-center">{t("hairpinDetail.colStatus")}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.label} className="border-b border-border">
                <td className="px-3 py-1.5">{r.label}</td>
                <td className="px-3 py-1.5 text-right font-mono">
                  {r.tm > 0 ? r.tm.toFixed(1) : "—"}
                </td>
                <td className="px-3 py-1.5 text-right font-mono">
                  {r.dg !== 0 ? r.dg.toFixed(1) : "—"}
                </td>
                <td className="px-3 py-1.5 text-center">
                  {r.tm <= 0 ? (
                    <span className="text-muted-foreground">—</span>
                  ) : r.tm > 40 ? (
                    <span className="inline-block px-1.5 py-0.5 rounded text-caption font-medium bg-warning/10 text-warning">
                      {t("hairpinDetail.statusWarn")}
                    </span>
                  ) : (
                    <span className="inline-block px-1.5 py-0.5 rounded text-caption font-medium bg-success/10 text-success">
                      {t("hairpinDetail.statusOk")}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {result.warnings.length > 0 && (
          <div className="mt-3 space-y-0.5 text-caption text-muted-foreground">
            <div className="font-semibold text-foreground">{t("hairpinDetail.warningsLabel")}</div>
            {result.warnings.map((w, i) => (
              <div key={i} className="text-warning">{w}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
