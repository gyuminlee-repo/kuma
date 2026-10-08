import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useAppStore } from "../../store/appStore";
import { isValidContactEmail } from "../../lib/contactEmail";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Label } from "../ui/label";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "../ui/dialog";

/**
 * Asks for the user's own contact email the first time a BLAST or InterProScan
 * submission needs one. EBI Job Dispatcher requires a submitter address; the
 * address is saved to Settings and sent to EBI only.
 *
 * Mounted next to NetworkConsentDialog. It only ever opens after consent,
 * because the sidecar reports a missing address in answer to a request that
 * consent already let through.
 */
export function ContactEmailDialog() {
  const { t } = useTranslation();
  const pending = useAppStore((s) => s.contactEmailPending);
  const saved = useAppStore((s) => s.settings?.network?.contact_email ?? "");
  const submitContactEmail = useAppStore((s) => s.submitContactEmail);
  const cancelContactEmail = useAppStore((s) => s.cancelContactEmail);
  const [value, setValue] = useState("");
  const [invalid, setInvalid] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (pending) {
      setValue(saved);
      setInvalid(false);
      setSaving(false);
    }
    // Only when the dialog opens: typing must not be overwritten by the store.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!isValidContactEmail(value)) {
      setInvalid(true);
      return;
    }
    setSaving(true);
    await submitContactEmail(value);
    setSaving(false);
  }

  return (
    <Dialog
      open={pending}
      onOpenChange={(open) => {
        if (!open) cancelContactEmail();
      }}
    >
      <DialogContent className="max-w-md" aria-describedby="contact-email-desc">
        <form noValidate onSubmit={(e) => void handleSubmit(e)} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>{t("contactEmail.title")}</DialogTitle>
            <DialogDescription id="contact-email-desc">
              {t("contactEmail.description")}
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="contact-email-input">{t("contactEmail.label")}</Label>
            <Input
              id="contact-email-input"
              type="email"
              autoComplete="email"
              autoFocus
              value={value}
              aria-invalid={invalid}
              aria-describedby={invalid ? "contact-email-error" : undefined}
              onChange={(e) => {
                setValue(e.target.value);
                setInvalid(false);
              }}
            />
            {invalid && (
              <p id="contact-email-error" role="alert" className="text-xs text-destructive">
                {t("contactEmail.invalid")}
              </p>
            )}
          </div>

          <DialogFooter className="flex gap-2 sm:flex-row">
            <Button type="button" variant="outline" size="sm" onClick={cancelContactEmail}>
              {t("contactEmail.btnCancel")}
            </Button>
            <Button type="submit" size="sm" disabled={saving}>
              {t("contactEmail.btnSave")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
