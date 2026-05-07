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
            외부 데이터베이스 사용 동의
          </DialogTitle>
          <DialogDescription id="network-consent-desc" asChild>
            <div className="space-y-3 text-sm text-muted-foreground">
              <p>
                이 기능은 다음 외부 서비스를 호출합니다. 입력한 서열 데이터가
                해당 서비스로 전송됩니다.
              </p>
              <ul
                className="list-disc pl-5 space-y-1 text-foreground"
                role="list"
                aria-label="외부 서비스 목록"
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
                동의는 재시작 후에도 유지됩니다. Settings에서 오프라인 모드를
                켜면 언제든지 외부 호출을 차단할 수 있습니다.
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
            취소
          </Button>
          <Button
            size="sm"
            onClick={grantNetworkConsent}
            autoFocus
          >
            동의하고 계속
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
