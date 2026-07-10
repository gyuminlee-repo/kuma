import { useTranslation } from "react-i18next";
import { useAppStore } from "../../store/appStore";
import { Dialog, DialogContent, DialogTitle } from "../ui/dialog";
import { DesignReportContent } from "./DesignReportContent";

export function DesignReport() {
  const { t } = useTranslation();
  const showReport = useAppStore((s) => s.showReport);
  const setShowReport = useAppStore((s) => s.setShowReport);
  const hasResults = useAppStore((s) => s.designResults.length > 0);

  if (!showReport || !hasResults) return null;

  return (
    <Dialog open={showReport} onOpenChange={setShowReport}>
      <DialogContent className="max-h-[80vh] max-w-2xl overflow-y-auto" aria-describedby={undefined}>
        <DialogTitle className="sr-only">{t("designReport.title")}</DialogTitle>
        <DesignReportContent onClose={() => setShowReport(false)} />
      </DialogContent>
    </Dialog>
  );
}
