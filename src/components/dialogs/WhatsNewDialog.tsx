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


interface WhatsNewDialogProps {
  /** Called when the user dismisses the modal. */
  onDismiss?: () => void;
}

export function WhatsNewDialog({ onDismiss }: WhatsNewDialogProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);

  // The release notes live in the locale files as a string array
  // (whatsNewDialog.highlights), generated into en.json from the CHANGELOG
  // "### Highlights" block and translated into the other locales.
  // `defaultValue: []` keeps a missing or malformed key from rendering the raw
  // key string, and the guards below keep a non-array value from crashing.
  const rawHighlights = t("whatsNewDialog.highlights", {
    returnObjects: true,
    defaultValue: [],
  });
  const highlights: string[] = Array.isArray(rawHighlights)
    ? rawHighlights.filter((item): item is string => typeof item === "string")
    : [];

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
      {/*
        The bullets are the only part allowed to grow: the modal is capped at
        85vh and laid out as a column, the header and the footer refuse to
        shrink, and the list takes whatever is left and scrolls. Without this
        the modal grew with its content and a long enough set of highlights
        pushed the "Got it" button off screen with no way to reach it. The
        English bullets run to about 93 characters and their translations to
        125 (fr) and 120 (pt-BR), so the overflow arrives in some languages and
        not others.
      */}
      <DialogContent
        className="flex max-h-[85vh] max-w-sm flex-col"
        aria-describedby="whats-new-desc"
      >
        <DialogHeader className="shrink-0">
          <DialogTitle>{t("whatsNewDialog.title", { version: __APP_VERSION__ })}</DialogTitle>
          <DialogDescription id="whats-new-desc">
            {t("whatsNewDialog.description")}
          </DialogDescription>
        </DialogHeader>

        {/*
          tabIndex makes the scroll container itself focusable (WCAG 2.1.1).
          It scrolls, it holds no focusable descendant, and Radix traps focus in
          the dialog while autoFocus puts it on "Got it", so without a tab stop
          of its own a keyboard-only user has no way to reach the overflow. The
          stop goes on the <ul> rather than on a wrapper: a focusable wrapper
          would need its own role and name, which a screen reader announces on
          top of the list it contains. Nothing else is added here either, since
          an aria-label would have to be an untranslated literal (the locale
          files are generated and hand-translated, not written here), and the
          dialog title and description already say what the list is.
        */}
        {highlights.length > 0 && (
          <ul
            className="min-h-0 list-disc space-y-1.5 overflow-y-auto pl-5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
            role="list"
            tabIndex={0}
          >
            {highlights.map((highlight, index) => (
              <li key={`${index}-${highlight}`} className="text-sm text-foreground">
                {highlight}
              </li>
            ))}
          </ul>
        )}

        <DialogFooter className="shrink-0">
          <Button size="sm" onClick={handleDismiss} autoFocus>
            {t("whatsNewDialog.gotItBtn")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
