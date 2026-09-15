# Spec: In-app help panel (KURO + MAME)

Date: 2026-09-15
Author: brainstorming session
Scope: one feature, one PR. Reference implementation surveyed: SBLIMS-ARCH (`arch.kbiofoundry.kr`).

## Context

kuma already carries a lot of help. What it does not carry is a place to look something up.

Present surfaces, all verified on `origin/main` at `e7dafbfc`:

| Surface | Where | Answers |
|---|---|---|
| `InlineHelp` `?` icons, 52 call sites | `src/components/ui/InlineHelp.tsx:21-79` | "what is this field" |
| `FormatPreviewHelp` | `src/components/ui/FormatPreviewHelp.tsx:294-327` | "what shape does this file take" |
| `GuidedTour`, 10 spots | `src/components/dialogs/GuidedTour.tsx` | "where is everything" |
| `Onboarding`, 1 page | `src/screens/Onboarding.tsx` | "what is this app" |
| `WhatsNewDialog` | `src/components/dialogs/WhatsNewDialog.tsx` | "what changed" |
| `SharedAboutDialog` | `src/components/layout/SharedAboutDialog.tsx` | "what version, what licences" |

None of them answers "how do I set up barcodes from the start" or "a well came back NO_CALL, what do I look at". Those are procedural and conceptual questions, and they need a surface that can be browsed rather than one that fires next to a field.

The Help menu has eight entries and none of them reaches a user guide (`src/components/layout/MenuBar.tsx:410-453`, `src/components/mame/layout/MenuBar.tsx:374-415`).

### What the reference implementation does

SBLIMS-ARCH puts help in a right slide-over panel, 440 px wide, full height, opened from a header button. The URL does not change and `x` returns the operator to the work. Inside the panel a grouped table of contents sits above the body: 7 groups, 11 topics. Cross-references inside the body are buttons rather than links, so following one swaps the topic without leaving the panel. A single `View all` link leads to `/help?topic=overview`, the same content in a wider layout.

Two properties matter for the design below. There is **no search** and there are **no images**: `input` count 0, `img` count 0 on both the panel and the full page. A topic body runs a few hundred characters. It is a manual digest rather than a documentation site.

A separate 18-step spotlight tour lives behind its own button. kuma already has that in `GuidedTour`.

## Decisions

### D1. Content comes from the step-aligned docs

In-app help renders `docs/kuro` (8 files) and `docs/mame` (6 files), 54.8 KB together. They map one-to-one onto the app steps, which is what makes context entry (D5) possible, and they are already about the right length.

`docs/en` and `docs/ko` (29 files each, 39.8 KB for the English half) are **out of scope**. They are topic-shaped rather than step-shaped and too long for a panel.

> Assumption: the overlap between `docs/kuro` and `docs/en` is not resolved here. Choosing which of the two survives is a larger decision than this work.

Both sets are currently excluded from the published site by `mkdocs.yml:7-18`, so `docs/en` and `docs/ko` reach neither the site nor the app today. That is a separate finding and is recorded rather than acted on.

### D2. Two languages, explicit fallback

`docs/help/ko` and `docs/help/en`, 14 topics each. The remaining eight locales fall back to English.

`docs/kuro` and `docs/mame` are written in Korean, so the English half is new translation work for all 14 topics.

Layout:

```
docs/help/
  ko/  kuro-index.md, kuro-01-load.md ... kuro-06-export.md,
       mame-index.md, mame-01-setup.md ... mame-04-activity.md, mame-pipeline.md
  en/  the same 14 names
```

### D3. Vite `?raw`, not Tauri resources

```ts
// src/help/content.ts
const ko = import.meta.glob("../../docs/help/ko/*.md", { query: "?raw", import: "default", eager: true })
const en = import.meta.glob("../../docs/help/en/*.md", { query: "?raw", import: "default", eager: true })
```

This avoids `tauri.conf.json` `bundle.resources` entirely. `AGENTS.md:263` bans glob patterns there, so the resource route would mean one hand-written line per file, plus keeping `sync-check`'s `tauri-resources` green. It also avoids a capability change and any runtime file read.

`import.meta.glob` is a Vite build-time feature and is unrelated to the Tauri resource glob ban, which governs the Tauri bundler.

The existing precedent for reading bundled text is `SharedAboutDialog.tsx:105-106`, which resolves and reads `resources/NOTICE.md`. That precedent exists because `NOTICE.md` is generated at build time by `scripts/build-notice.mjs` and is gitignored, so Vite cannot import it. Help markdown is committed source and carries no such constraint.

Cost: about 110 KB into the JS bundle, against an 85 MB installer.

`vite-env.d.ts` needs a module declaration for `*.md?raw`.

### D4. `react-markdown`

The repository has no markdown renderer (`react-markdown`, `marked`, `markdown-it`, `remark`, `micromark`, `dompurify` all absent from `package.json`). `react-markdown` renders to React elements without `dangerouslySetInnerHTML`, so it does not fight the CSP in `tauri.conf.json` `app.security.csp` and needs no sanitiser of our own.

A hand-rolled parser is rejected: the repository rule is to reach for an established implementation first, and a parser we wrote would need its own correctness corpus.

Cross-references are written in the markdown as ordinary relative links:

```markdown
See [Barcode setup](mame-01-setup.md).
```

The renderer overrides the `a` component. A link ending in `.md` swaps the active topic inside the panel and does not navigate. Only `http(s)` links leave, through the opener.

### D5. Right slide-over, shared between tabs, context-aware

440 px fixed width, full height, no URL change, `x` closes and returns. One shared component used by both tabs, in the manner of `SharedAboutDialog`. Entry is a new item in the Help menu of both menu bars.

Table of contents, four groups:

| Group | Topics |
|---|---|
| Getting started | KURO overview, MAME overview |
| KURO design | Load, Mutations, Parameters, Submit, Results, Export |
| MAME verification | Barcode setup, Analyze and review, Janus, Activity |
| Deeper | MAME pipeline |

Opening the panel selects the topic matching the current step. On MAME `analyze.review` the panel opens at "Analyze and review". Step identifiers already exist: `src/components/mame/layout/MameWorkflowRail.tsx:24-32` and `src/components/steps/constants.ts:9-18`. This is the reason D1 chose step-aligned content.

No search and no images, following the reference implementation. Fourteen topics are covered by the table of contents, and leaving images out keeps the bundle question closed.

## Error handling

Locale resolution is requested locale, then `en`, then `ko`. When none holds the topic, the body shows "this topic is not translated yet" and the table of contents stays usable rather than the panel going blank.

**A fallback is shown as a fallback.** When the panel renders English to a Korean user it says so. Rendering another language silently would let a reader believe a translation exists.

## i18n

Markdown lives outside the locale JSON, so it does not touch the untranslated ratchet in `scripts/i18n-parity.mjs`, which fails a build when a locale carries too many values byte-identical to English. Pasting prose into ten locale files would break that ratchet; markdown files do not.

What does enter the locale JSON is panel chrome: title, four group labels, topic labels, close, and the fallback notice. Roughly fifteen short keys, translated into all ten locales as usual.

## Testing

| Check | Fails when |
|---|---|
| Topic inventory | a topic is missing from `ko` or `en` |
| TOC agreement | the table of contents and the file set disagree |
| Cross-reference integrity | a `.md` link points at a topic that does not exist |
| Context entry | opening the panel on a step selects the wrong topic |
| Fallback | a missing locale file blanks the panel or hides the notice |
| Content presence | a `?raw` import yields an empty string |

Content presence is worth stating: a mistyped glob returns an empty object and every topic renders blank while every other test passes.

## Drift

`docs/help/ko` is moved from `docs/kuro` and `docs/mame`, which stay for the published site. Two copies drift. They are tied together in `.cross-layer-sync.json` so `sync-check-groups` reports it.

## Definition of done

- `pytest tests/` 0 failed
- `basedpyright` at the `main` baseline of 2 errors, both pre-existing in `scripts/gen-font-metrics.py`
- `node node_modules/typescript/bin/tsc --noEmit` exit 0, no new `as any` or `@ts-ignore`
- vitest 0 failed
- `i18n-lint`, `i18n-parity`, `sync-check-groups` pass
- the app is launched and the panel opened by eye, on both tabs

## Assumption ledger

| # | Assumption | Blast radius | Status |
|---|---|---|---|
| 1 | `docs/kuro` and `docs/en` overlap is left alone | content architecture | user informed, deferred |
| 2 | `docs/en` and `docs/ko` stay unpublished and unbundled | 58 files remain dead | recorded, not acted on |
| 3 | Eight locales read English rather than their own language | non-Korean non-English operators | user chose two languages |
| 4 | No search | findability across 14 topics | matches reference implementation |
| 5 | No images | comprehension of spatial steps | matches reference implementation |
| 6 | `docs/help/ko` duplicates the mkdocs sources rather than replacing them | drift risk, mitigated by the sync group | unconfirmed |

## Out of scope

- Resolving the `docs/en` and `docs/ko` duplication
- Publishing changes to `mkdocs.yml`
- Search
- Screenshots and video
- Replacing `InlineHelp`, `GuidedTour` or `Onboarding`
