# @qa/tokens

One source of truth for the QA Ecosystem's look — LinkSpy today, the Dashboard
and Board app next. Values come verbatim from `linkspy-issue-primitive.html`'s
`:root`.

Two artefacts, same values:
- **`tokens.css`** — CSS custom properties. The runtime source; import once at
  the app root, then reference `var(--violet)` etc.
- **`tokens.ts`** — the same values, typed, for a Tailwind theme / inline styles
  / SVG. A test asserts the two never drift.

> No monorepo here yet, so this is a standalone package consumed by path. When a
> workspace exists, it lifts out unchanged. Wiring it in as the Tailwind theme is
> Phase 3 — this phase only establishes the set.

## The six type sizes

The whole system uses **six** sizes. Weight and colour carry hierarchy — never a
seventh size, never a half-pixel tweak.

| Token       | px     | Used for |
|-------------|--------|----------|
| `--text-xs` | 11     | micro-labels, eyebrows, `kbd`, group headers |
| `--text-sm` | 12.5   | meta lines, captions, secondary rows |
| `--text-md` | 14     | body, controls — the default |
| `--text-lg` | 17     | card / detail titles |
| `--text-xl` | 22     | section headlines, empty-state H2 |
| `--text-2xl`| 28     | banner site name, report H1 |

**Collapse map** (prototype had ~12 sizes; each maps to the nearest of six):

| Prototype px seen        | → token |
|--------------------------|---------|
| 9.5, 10, 10.5, 11, 11.5  | `xs` (11) |
| 12, 12.5, 13             | `sm` (12.5) |
| 13.5, 14, 14.5, 15       | `md` (14) |
| 17                       | `lg` (17) |
| 22, 23                   | `xl` (22) |
| 26, 27, 30               | `2xl` (28) |

## Hard rules (enforced in review)

1. **Gradients appear in exactly three places** — the score ring, the primary
   button, and the selection spine. Nowhere else. Health-bar segments are **flat**
   (`#4FC098` / `#C8384C` / `#D89422`). `GRADIENT_ALLOWLIST` names the three.
2. **Violet is selection / active / interactive only** — never a status. A red
   thing is red because it's broken, not because it's violet.
3. **Status is its own language**: `--red` / `--green` / `--amber`, each with a
   `-bg` pair. Independent of the accent.
4. **Tabular numerals on every numeric UI** — counts must not jitter as they change.
5. **Six sizes** (above). Nothing else.

## Usage

```css
/* app root, once */
@import "@qa/tokens/tokens.css";

.card { background: var(--card); box-shadow: var(--shadow); border-radius: var(--radius-card); }
.title { font-size: var(--text-lg); color: var(--ink); }
```

```ts
import { color, shadow, fontSize, pageBackground } from "@qa/tokens";
// e.g. a Tailwind theme: colors: { violet: color.violet, ink: color.ink, … }
```
