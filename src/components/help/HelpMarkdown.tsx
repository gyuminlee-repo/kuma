import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
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
 *
 * Tables come from the GFM extension, and each sits in a scrolling wrapper so a
 * wide one stays inside the narrow panel. Raw HTML is dropped rather than
 * escaped, which keeps authoring comments in the topics off the screen.
 */
export function HelpMarkdown({ body, knownTopics, onTopicChange }: HelpMarkdownProps) {
  return (
    <div className="space-y-2 text-sm leading-relaxed [&_h1]:mt-1 [&_h1]:text-base [&_h1]:font-semibold [&_h2]:mt-4 [&_h2]:font-semibold [&_h3]:mt-3 [&_h3]:font-medium [&_ul]:list-disc [&_ul]:pl-5 [&_code]:rounded [&_code]:bg-muted/30 [&_code]:px-1 [&_pre]:overflow-x-auto [&_pre]:rounded [&_pre]:bg-muted/30 [&_pre]:p-2 [&_pre]:text-xs [&_pre_code]:bg-transparent [&_pre_code]:px-0 [&_table]:border-collapse [&_th]:border [&_th]:border-border [&_th]:px-2 [&_th]:py-1 [&_th]:text-left [&_th]:font-medium [&_td]:border [&_td]:border-border [&_td]:px-2 [&_td]:py-1">
      <Markdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{
          table({ children }) {
            return (
              <div className="overflow-x-auto">
                <table>{children}</table>
              </div>
            );
          },
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
