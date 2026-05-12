/**
 * WhatsNewDialog — shown once per app version on first launch after an update.
 *
 * Persistence:
 *   localStorage key  : "kuma:lastSeenVersion"
 *   Value             : semver string, e.g. "0.2.1"
 *
 * Behaviour:
 *   - On mount: compare localStorage value against __APP_VERSION__.
 *     • If stored value is absent (first-ever launch), write current version
 *       and do NOT show the modal (first-run onboarding already handles this).
 *     • If stored value differs from current, show the modal.
 *   - On dismiss ("Got it"): write current version to localStorage, close.
 */
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";

declare const __APP_VERSION__: string;

const STORAGE_KEY = "kuma:lastSeenVersion";

interface WhatsNewItem {
  label: string;
  detail: string;
}

const WHATS_NEW_ITEMS: WhatsNewItem[] = [
  {
    label: "Colorblind assist (kuro)",
    detail:
      "Shape-prefix toggleable color assist is now available in kuro (previously mame-only). Enable via About → Accessibility.",
  },
  {
    label: "Inline help (?)",
    detail:
      "Parameter fields now have inline (?) help tooltips explaining valid ranges and recommended values.",
  },
  {
    label: "Keyboard shortcut table",
    detail:
      "All keyboard shortcuts are listed in About → Keyboard Shortcuts for quick reference.",
  },
  {
    label: "What's New modal",
    detail:
      "You are looking at it. This modal appears once per version after an update.",
  },
];

interface WhatsNewDialogProps {
  /** Called when the user dismisses the modal. */
  onDismiss?: () => void;
}

export function WhatsNewDialog({ onDismiss }: WhatsNewDialogProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === null) {
      // First-ever launch — record version, skip modal.
      localStorage.setItem(STORAGE_KEY, __APP_VERSION__);
      return;
    }
    if (stored !== __APP_VERSION__) {
      setOpen(true);
    }
  }, []);

  function handleDismiss() {
    localStorage.setItem(STORAGE_KEY, __APP_VERSION__);
    setOpen(false);
    onDismiss?.();
  }

  return (
    <Dialog open={open} onOpenChange={(next) => { if (!next) handleDismiss(); }}>
      <DialogContent
        className="max-w-sm"
        aria-describedby="whats-new-desc"
      >
        <DialogHeader>
          <DialogTitle>{t("whatsNewDialog.title", { version: __APP_VERSION__ })}</DialogTitle>
          <DialogDescription id="whats-new-desc">
            {t("whatsNewDialog.description")}
          </DialogDescription>
        </DialogHeader>

        <ul className="space-y-2" role="list">
          {WHATS_NEW_ITEMS.map((item) => (
            <li key={item.label} className="flex flex-col gap-0.5">
              <span className="text-sm font-semibold text-foreground">
                {item.label}
              </span>
              <span className="text-xs text-muted-foreground">{item.detail}</span>
            </li>
          ))}
        </ul>

        <DialogFooter>
          <Button size="sm" onClick={handleDismiss} autoFocus>
            {t("whatsNewDialog.gotItBtn")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
