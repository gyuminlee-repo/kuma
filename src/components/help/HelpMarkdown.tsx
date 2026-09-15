import Markdown from "react-markdown";
import { openUrl } from "@tauri-apps/plugin-opener";

interface HelpMarkdownProps {
  body: string;
  knownTopics: string[];
  onTopicChange: (id: string) => void;
}

/**
 * Markdown for the help panel, with the link rule the spec fixes in C2.
 *
 * The rule runs in order: an absolute link leaves through the opener, a link
 * naming a topic swaps the panel, and anything else renders as text. The third
 * branch is why a broken cross-reference shows as words rather than as a link
 * that does nothing when clicked.
 */
export function HelpMarkdown({ body, knownTopics, onTopicChange }: HelpMarkdownProps) {
  return (
    <div className="space-y-2 text-sm leading-relaxed [&_h2]:mt-4 [&_h2]:font-semibold [&_h3]:mt-3 [&_h3]:font-medium [&_ul]:list-disc [&_ul]:pl-5 [&_code]:rounded [&_code]:bg-muted/30 [&_code]:px-1">
      <Markdown
        components={{
          a({ href, children }) {
            const target = href ?? "";
            if (target.startsWith("http://") || target.startsWith("https://")) {
              return (
                <a
                  href={target}
                  onClick={(e) => {
                    e.preventDefault();
                    void openUrl(target);
                  }}
                >
                  {children}
                </a>
              );
            }
            if (target.endsWith(".md")) {
              const stem = (target.split("/").pop() ?? "").slice(0, -3);
              if (knownTopics.includes(stem)) {
                return (
                  <button type="button" className="underline" onClick={() => onTopicChange(stem)}>
                    {children}
                  </button>
                );
              }
            }
            return <>{children}</>;
          },
        }}
      >
        {body}
      </Markdown>
    </div>
  );
}
