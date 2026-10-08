export type HelpLocale = "ko" | "en";

// The generic overload of import.meta.glob (vite/types/importGlob.d.ts) types
// the eager result as Record<string, string>, so no module declaration or cast
// is needed.
const RAW_KO = import.meta.glob<string>("../../docs/help/ko/*.md", {
  query: "?raw",
  import: "default",
  eager: true,
});

const RAW_EN = import.meta.glob<string>("../../docs/help/en/*.md", {
  query: "?raw",
  import: "default",
  eager: true,
});

/** Path to topic id: the file stem, which is what cross-references name. */
function byStem(raw: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [path, body] of Object.entries(raw)) {
    const stem = path.split("/").pop()?.replace(/\.md$/, "");
    if (stem) out[stem] = body;
  }
  return out;
}

const BODIES: Record<HelpLocale, Record<string, string>> = {
  ko: byStem(RAW_KO),
  en: byStem(RAW_EN),
};

/**
 * The order a request is served in after the requested locale. The app has
 * ten locales and help has two, so eight of them land on English. Korean is
 * last rather than absent because it is the language the topics were written
 * in, and a Korean body a reader cannot read beats a blank panel.
 */
const CHAIN: HelpLocale[] = ["en", "ko"];

export interface TopicBody {
  body: string;
  /** The locale actually served, or null when no locale holds the topic. */
  usedLocale: HelpLocale | null;
  /** True when the served locale is not the one asked for. */
  fellBack: boolean;
}

/** "ko-KR", "ko_KR" and "KO" all ask for Korean help. */
function baseLanguage(tag: string): string {
  return tag.toLowerCase().split(/[-_]/)[0];
}

function isHelpLocale(value: string): value is HelpLocale {
  return value === "ko" || value === "en";
}

export function getTopicBody(id: string, requested: string): TopicBody {
  const base = baseLanguage(requested);
  const asked: HelpLocale | null = isHelpLocale(base) ? base : null;
  if (asked && BODIES[asked][id]) {
    return { body: BODIES[asked][id], usedLocale: asked, fellBack: false };
  }
  for (const loc of CHAIN) {
    if (BODIES[loc][id]) {
      return { body: BODIES[loc][id], usedLocale: loc, fellBack: true };
    }
  }
  return { body: "", usedLocale: null, fellBack: false };
}

export function listLoadedTopics(locale: HelpLocale): string[] {
  return Object.keys(BODIES[locale]);
}
