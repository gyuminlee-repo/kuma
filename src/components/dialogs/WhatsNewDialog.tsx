/**
 * WhatsNewDialog, shown once per app version on first launch after an update.
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
 *
 * What it shows is every release from the one after the stored version through
 * the one now running, newest first, rather than the newest release alone. An
 * operator who updates once after skipping three releases was previously told
 * about one of them and had no route to the rest from inside the app. The
 * bullets of past releases come from `whatsNewDialog.releases` in the locale
 * files, an archive keyed by version that scripts/gen-whatsnew.mjs generates
 * from CHANGELOG.md.
 *
 * The list scrolls, since the range has no upper bound: an operator returning
 * from a year-old build gets every release in between.
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

/**
 * Order two version strings numerically, part by part.
 *
 * The stored value is whatever an older build wrote, so it may carry fewer parts
 * than the archive keys ("0.16" against "0.16.9"), more of them ("0.15.15.01"),
 * or a suffix a dev build added ("0.0.0-test"). A missing part counts as 0 and a
 * part that is not a number counts as 0 as well, which keeps a suffixed build on
 * the same footing as the release it was cut from instead of dropping it out of
 * every comparison.
 */
function compareVersions(a: string, b: string): number {
  const pa = a.split(".");
  const pb = b.split(".");
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const na = Number.parseInt(pa[i] ?? "0", 10);
    const nb = Number.parseInt(pb[i] ?? "0", 10);
    const va = Number.isNaN(na) ? 0 : na;
    const vb = Number.isNaN(nb) ? 0 : nb;
    if (va !== vb) return va - vb;
  }
  return 0;
}

/** One release as the modal renders it. */
interface ReleaseSection {
  version: string;
  items: string[];
}

/**
 * The releases to show: everything after `since` up to and including `current`,
 * newest first.
 *
 * Two edges matter and both resolve to "show what there is". A stored version
 * older than anything in the archive (the archive starts at the release that
 * introduced these notes) yields every entry rather than none. A stored version
 * at or above the current one, which happens on a downgrade, yields nothing, and
 * the caller falls back to the current release's own bullets rather than opening
 * an empty modal.
 */
function sectionsFor(
  archive: Record<string, string[]>,
  since: string | null,
  current: string,
): ReleaseSection[] {
  return Object.entries(archive)
    .filter(
      ([version, items]) =>
        Array.isArray(items) &&
        items.length > 0 &&
        compareVersions(version, current) <= 0 &&
        (since === null || compareVersions(version, since) > 0),
    )
    .map(([version, items]) => ({
      version,
      items: items.filter((item): item is string => typeof item === "string"),
    }))
    .sort((x, y) => compareVersions(y.version, x.version));
}

interface WhatsNewDialogProps {
  /** Called when the user dismisses the modal. */
  onDismiss?: () => void;
  /**
   * The version being run. Defaults to the build's own, which is what the app
   * passes; it is a parameter because the range this modal shows is a function
   * of it, and __APP_VERSION__ is substituted at build time and so cannot be
   * varied to exercise that range.
   */
  currentVersion?: string;
}

export function WhatsNewDialog({
  onDismiss,
  currentVersion = __APP_VERSION__,
}: WhatsNewDialogProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [lastSeen, setLastSeen] = useState<string | null>(null);

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

  // The per-version archive backing the range. Same guards, one level deeper:
  // a malformed value must render nothing rather than crash the modal that
  // reports the update.
  const rawReleases = t("whatsNewDialog.releases", {
    returnObjects: true,
    defaultValue: {},
  });
  const archive: Record<string, string[]> =
    rawReleases !== null && typeof rawReleases === "object" && !Array.isArray(rawReleases)
      ? (rawReleases as Record<string, string[]>)
      : {};

  const ranged = sectionsFor(archive, lastSeen, currentVersion);
  // Falling back to the current release's own bullets covers an archive that has
  // no entry for this build (a dev version, or a release whose notes were not
  // generated) and a stored version that is not older than the current one.
  const sections: ReleaseSection[] =
    ranged.length > 0
      ? ranged
      : highlights.length > 0
        ? [{ version: currentVersion, items: highlights }]
        : [];
  const multiple = sections.length > 1;

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === null) {
      // First-ever launch, record version, skip modal.
      localStorage.setItem(STORAGE_KEY, currentVersion);
      return;
    }
    if (stored !== currentVersion) {
      setLastSeen(stored);
      setOpen(true);
    }
  }, []);

  function handleDismiss() {
    localStorage.setItem(STORAGE_KEY, currentVersion);
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
        className="flex max-h-[85vh] max-w-md flex-col"
        aria-describedby="whats-new-desc"
      >
        <DialogHeader className="shrink-0">
          <DialogTitle>{t("whatsNewDialog.title", { version: currentVersion })}</DialogTitle>
          <DialogDescription id="whats-new-desc">
            {multiple && lastSeen !== null
              ? t("whatsNewDialog.descriptionRange", { from: lastSeen })
              : t("whatsNewDialog.description")}
          </DialogDescription>
        </DialogHeader>

        {/*
          tabIndex makes the scroll container itself focusable (WCAG 2.1.1).
          It scrolls, it holds no focusable descendant, and Radix traps focus in
          the dialog while autoFocus puts it on "Got it", so without a tab stop
          of its own a keyboard-only user has no way to reach the overflow.
          Nothing else is added here, since an aria-label would have to be an
          untranslated literal (the locale files are generated and
          hand-translated, not written here), and the dialog title and
          description already say what the list is. The stop sits on this
          wrapper rather than on a list because a range of releases is several
          lists with a version heading each, and moving the stop per release
          would make the number of tab stops depend on how many releases were
          skipped. The wrapper stays a plain div with no role of its own, so a
          screen reader announces the headings and lists inside it and not a
          container wrapped around them.
        */}
        {sections.length > 0 && (
          <div
            className="min-h-0 space-y-4 overflow-y-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
            tabIndex={0}
          >
            {sections.map((section) => (
              <section key={section.version}>
                {/*
                  The version heading appears only for a range. A single release
                  already has its version in the dialog title, and repeating it
                  directly underneath reads as a second, different statement.
                */}
                {multiple && (
                  <h3 className="mb-1.5 text-xs font-semibold text-muted-foreground">
                    v{section.version}
                  </h3>
                )}
                <ul className="list-disc space-y-1.5 pl-5" role="list">
                  {section.items.map((highlight, index) => (
                    <li key={`${index}-${highlight}`} className="text-sm text-foreground">
                      {highlight}
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
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
