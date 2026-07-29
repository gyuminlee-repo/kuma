# kuma Design System

## 1. Atmosphere & Identity

kuma is a quiet scientific workbench: dense, persistent, and task-focused. The signature is a two-tool command surface where Kuro, Mame, and EVOLVEpro keep distinct muted accents while sharing the same shell, forms, rails, dialogs, and autosave feedback.

## 2. Color

### Palette

| Role | Token | Light | Dark | Usage |
|---|---|---|---|---|
| Surface / app | `--background` | `210 40% 96.1%` | `222.2 47% 7%` | Root background |
| Surface / card | `--card` | `0 0% 100%` | `222.2 47% 9%` | Cards, panels, dialogs |
| Surface / popover | `--popover` | `0 0% 100%` | `222.2 47% 11%` | Menus and popovers |
| Text / primary | `--foreground` | `220 22% 12%` | `210 40% 96%` | Main UI text |
| Text / muted | `--muted-foreground` | `220 10% 40%` | `215 20% 65%` | Captions and helper text |
| Border / input | `--border`, `--input` | `30 14% 88%` | `222.2 47% 18%` | Dividers, fields, outlines |
| Kuro accent | `[data-tool="kuro"] --primary` | `221.1 13.5% 27.6%` | `221.1 13.5% 70%` | Kuro CTAs and focus |
| Mame accent | `[data-tool="mame"] --primary` | `27.4 16.7% 41.0%` | `27.4 16.7% 70%` | Mame CTAs and focus |
| EVOLVEpro accent | `[data-tool="evolvepro"] --primary` | `168 35% 30%` | `168 30% 62%` | EVOLVEpro CTAs and focus |
| Success | `--color-success` | `oklch(0.65 0.15 145)` | `oklch(0.72 0.15 145)` | Confirmations |
| Warning | `--color-warning` | `oklch(0.72 0.15 75)` | `oklch(0.78 0.15 75)` | Cautions |
| Error | `--color-error` | `oklch(0.55 0.20 25)` | `oklch(0.65 0.20 25)` | Errors and destructive states |
| Info | `--color-info` | `oklch(0.60 0.12 250)` | `oklch(0.70 0.12 250)` | Informational states |

### Rules

- Use Tailwind semantic colors from `tailwind.config.js`; add raw colors only by extending the CSS variable set first.
- Tool accents identify the active domain and should not be used as decoration.
- Status colors communicate state only: success, warning, error, info.

## 3. Typography

### Scale

| Level | Token / Class | Size | Usage |
|---|---|---|---|
| Page title | Tailwind `text-3xl` to `text-5xl` | 30-48px | Home and onboarding titles |
| Panel title | `--text-title`, `text-title` | 15px | Fixed shell and panel headings |
| Body | `--text-body`, `text-body` | 14px | Default application text |
| Body small | `text-sm` | 14px | Form text and descriptions |
| Caption | `--text-caption`, `text-caption` | 12px | Labels, metadata, status rows |
| Plate text | `--text-plate`, `--text-plate-tiny` | 10px / 8px | Well plate labels |

### Font Stack

- Primary: `-apple-system, BlinkMacSystemFont, "Segoe UI Variable", "Segoe UI", "Apple SD Gothic Neo", "Noto Sans KR", "Helvetica Neue", Arial, sans-serif`
- Mono: system monospace via Tailwind `font-mono`

### Rules

- Body text stays at 14px or larger.
- Data-heavy rows and path previews may use caption sizing only when space is constrained.
- Long paths and technical identifiers should truncate or wrap intentionally, never overflow.

## 4. Spacing & Layout

### Base Unit

All spacing follows a 4px scale already declared in `src/index.css`.

| Token | Value | Usage |
|---|---:|---|
| `--space-1` | 4px | Icon-to-label gaps |
| `--space-2` | 8px | Compact rows |
| `--space-3` | 12px | Field groups |
| `--space-4` | 16px | Form and card internals |
| `--space-5` | 20px | Comfortable group gaps |
| `--space-6` | 24px | Section padding |
| `--space-8` | 32px | Major group separation |

### Shell Metrics

| Token | Value | Usage |
|---|---:|---|
| `--header-h` | 48px | Global app header |
| `--menubar-h` | 40px | Tool menu bar |
| `--statusbar-h` | 24px | Status bar |
| `--sidebar-w` | 320px | Workflow rail |
| `--control-h` | 32px | Compact controls |
| `--control-h-primary` | 36px | Primary task controls |
| `--content-max-w` | 56rem | Wizard body limiter |

### Rules

- App shells use fixed chrome plus one named scroll owner per region.
- Wizard bodies own scroll between fixed header and footer.
- Split panes must use `min-h-0` / `min-w-0` on shrinkable children.
- Primary content must reflow without horizontal page scroll at 375px.

## 5. Components

### Button
- **Structure**: shared `Button` with Radix Slot support.
- **Variants**: default, destructive, outline, secondary, ghost, link.
- **States**: hover, focus-visible, disabled, loading via inline spinner when needed.
- **Accessibility**: visible focus ring, `disabled` for unavailable actions, `aria-busy` for running actions.

### Dialog
- **Structure**: Radix dialog portal, overlay, content, header, footer.
- **Variants**: confirmation, validation, settings, shortcuts, guided tour.
- **States**: open/closed animation, focus trap from Radix, explicit close/cancel actions.
- **Layout**: modal content scrolls internally when needed; app shell behind dialog is inert through Radix semantics or explicit tour handling.

### WizardContainer
- **Structure**: fixed header, scrollable body, fixed footer.
- **States**: previous disabled, next disabled, validation dialog for blocked progression.
- **Accessibility**: footer has progress label; validation dialog lists missing fields.
- **Layout**: scroll-body-shell; body max width varies by screen.

### File Picker Row
- **Structure**: label + state badge, readonly path field, browse icon button, helper text, basename preview.
- **States**: empty, ready, optional, disabled via parent action.
- **Accessibility**: label or aria-label on browse button, title carries full path.

### Workflow Rail
- **Structure**: vertical navigation list with active/done/pending badges.
- **States**: active, done, pending.
- **Accessibility**: tab semantics, arrow/Home/End keyboard navigation.

### Inspector / Drawer Strip
- **Structure**: compact key-value rows and callouts.
- **States**: empty, populated, selected record.
- **Rules**: never show fabricated example values as live data.

## 6. Motion & Interaction

| Type | Token | Duration | Usage |
|---|---|---:|---|
| Fast | `--duration-fast` | 150ms | Button and hover transitions |
| Base | `--duration-base` | 200ms | Dialog and panel state changes |

- Respect `prefers-reduced-motion`; the CSS tokens already collapse durations to `0ms`.
- Animate opacity and transform only.
- Every interactive control needs a visible focus state.

## 7. Depth & Surface

Strategy: mixed borders plus controlled floating shadows.

| Token | Value | Usage |
|---|---|---|
| `--shadow-hairline` | `0 1px 0 rgb(0 0 0 / 4%)` | Subtle separators |
| `--shadow-popover` | `0 8px 24px -8px ...` | Menus and popovers |
| `--shadow-dialog` | `0 20px 40px -12px ...` | Dialogs |
| `--shadow-floating` | `0 12px 32px rgba(24,24,27,0.10)` | Floating UI |

Use borders for in-flow panels and shadows only for floating layers.

## 8. Accessibility Constraints & Accepted Debt

### Constraints

- Target WCAG 2.2 AA.
- All form inputs have labels or explicit `aria-label`.
- Keyboard users can reach dialogs, menus, wizard navigation, and route selectors.
- CJK copy must not clip or wrap into orphaned one-character endings in compact panels.
- No new hidden state may rely only on color; use text, badges, or icons.

### Accepted Debt

| Item | Location | Why accepted | Owner / Exit |
|---|---|---|---|
| React dev tooling gate not installed | `package.json`, `src/main.tsx` | Existing production app; this PR focuses on user-facing convenience and avoids adding new dev-only dependencies without explicit project policy. | Add in a dedicated tooling PR. |
