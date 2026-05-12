import { useTranslation } from "react-i18next";
import { useAppStore } from "../../store/appStore";
import { Button } from "../ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "../ui/dialog";

/**
 * 외부 데이터베이스 사용 동의 모달.
 * AppLayout / MameLayout 루트에 마운트해 두고 store 상태로 열림 여부를 제어한다.
 */
export function NetworkConsentDialog() {
  const { t } = useTranslation();
  const pending = useAppStore((s) => s.networkConsentPending);
  const grantNetworkConsent = useAppStore((s) => s.grantNetworkConsent);
  const denyNetworkConsent = useAppStore((s) => s.denyNetworkConsent);

  return (
    <Dialog
      open={pending}
      onOpenChange={(open) => {
        // 사용자가 ESC 또는 오버레이 클릭으로 닫을 경우 거부로 처리
        if (!open) denyNetworkConsent();
      }}
    >
      <DialogContent
        className="max-w-md"
        aria-labelledby="network-consent-title"
        aria-describedby="network-consent-desc"
      >
        <DialogHeader>
          <DialogTitle id="network-consent-title">
            {t("networkConsent.title")}
          </DialogTitle>
          <DialogDescription id="network-consent-desc" asChild>
            <div className="space-y-3 text-sm text-muted-foreground">
              <p>
                {t("networkConsent.description")}
              </p>
              <ul
                className="list-disc pl-5 space-y-1 text-foreground"
                role="list"
                aria-label={t("networkConsent.serviceListAriaLabel")}
              >
                <li>
                  <span className="font-medium">UniProt</span>
                  {" — "}
                  <a
                    href="https://www.uniprot.org"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    uniprot.org
                  </a>
                  {" — protein sequence search"}
                </li>
                <li>
                  <span className="font-medium">NCBI BLAST (EBI)</span>
                  {" — "}
                  <a
                    href="https://www.ebi.ac.uk"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    ebi.ac.uk
                  </a>
                  {" — sequence similarity search"}
                </li>
                <li>
                  <span className="font-medium">AlphaFold (EBI)</span>
                  {" — "}
                  <a
                    href="https://alphafold.ebi.ac.uk"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    alphafold.ebi.ac.uk
                  </a>
                  {" — structure prediction lookup"}
                </li>
                <li>
                  <span className="font-medium">InterPro / Pfam (EBI)</span>
                  {" — "}
                  <a
                    href="https://www.ebi.ac.uk/interpro"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    ebi.ac.uk/interpro
                  </a>
                  {" — protein domain annotation"}
                </li>
              </ul>
              <p className="text-xs">
                {t("networkConsent.persistNote")}
              </p>
            </div>
          </DialogDescription>
        </DialogHeader>

        <DialogFooter className="flex gap-2 sm:flex-row">
          <Button
            variant="outline"
            size="sm"
            onClick={denyNetworkConsent}
          >
            {t("networkConsent.btnCancel")}
          </Button>
          <Button
            size="sm"
            onClick={grantNetworkConsent}
            autoFocus
          >
            {t("networkConsent.btnAccept")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
