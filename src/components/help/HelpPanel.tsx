import { useEffect, useId, useRef } from "react";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { HELP_GROUPS, ALL_TOPIC_IDS } from "@/help/topics";
import { getTopicBody } from "@/help/content";
import { HelpMarkdown } from "./HelpMarkdown";

interface HelpPanelProps {
  open: boolean;
  topic: string;
  onTopicChange: (id: string) => void;
  onClose: () => void;
}

/**
 * The help panel holds no state and knows nothing about steps. Each tab passes
 * the topic it derived from its own store, which is what keeps the panel usable
 * from two trees whose stores never meet.
 *
 * It is not modal: the screen behind it stays usable, so there is no overlay
 * and no focus trap. Opening moves focus to the close button so a keyboard
 * reader lands inside the panel, and Escape closes it from anywhere.
 */
export function HelpPanel({ open, topic, onTopicChange, onClose }: HelpPanelProps) {
  const { t, i18n } = useTranslation();
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const { body, usedLocale, fellBack } = getTopicBody(topic, i18n.language);

  return (
    <div
      role="dialog"
      aria-modal="false"
      aria-labelledby={titleId}
      className="fixed inset-y-0 right-0 z-40 flex w-[440px] max-w-full flex-col border-l border-border bg-card text-card-foreground shadow-lg"
    >
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 id={titleId} className="text-sm font-semibold">
          {t("help.panel.title")}
        </h2>
        <button
          ref={closeRef}
          type="button"
          aria-label={t("help.panel.close")}
          onClick={onClose}
          className="rounded p-1 text-muted-foreground hover:text-foreground"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>

      <nav aria-labelledby={titleId} className="border-b border-border px-4 py-2">
        {HELP_GROUPS.map((g) => (
          <div key={g.labelKey} className="mb-2">
            <div className="text-xs text-muted-foreground">{t(g.labelKey)}</div>
            <div className="flex flex-wrap gap-x-3 gap-y-1 text-sm">
              {g.topics.map((id) => (
                <button
                  key={id}
                  type="button"
                  aria-current={id === topic ? "true" : undefined}
                  onClick={() => onTopicChange(id)}
                  className={id === topic ? "font-semibold underline" : "hover:underline"}
                >
                  {t(`help.panel.topic.${id}`)}
                </button>
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className="flex-1 overflow-y-auto px-4 py-3">
        {usedLocale === null ? (
          <p data-testid="help-missing-topic" className="text-sm text-muted-foreground">
            {t("help.panel.notTranslated")}
          </p>
        ) : (
          <>
            {fellBack && (
              <p data-testid="help-fallback-notice" className="mb-2 text-xs text-muted-foreground">
                {usedLocale === "en"
                  ? t("help.panel.shownInEnglish")
                  : t("help.panel.shownInKorean")}
              </p>
            )}
            <HelpMarkdown body={body} knownTopics={ALL_TOPIC_IDS} onTopicChange={onTopicChange} />
          </>
        )}
      </div>
    </div>
  );
}
