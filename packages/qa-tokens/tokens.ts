/**
 * QA Ecosystem design tokens — typed source of truth.
 *
 * Mirrors tokens.css exactly. Import this where you need values in TS (a
 * Tailwind theme, an inline style, a canvas/SVG colour). The CSS file is the
 * runtime source; this is the same values, typed, so the two never drift —
 * `assertTokensMatch` in the test guards that.
 */
export const color = {
  violet: "#4F46E5",
  violetHover: "#4038CE",
  violetDeep: "#3D2FBF",
  violetSoft: "#E4E1FC",
  violetSofter: "#EFEDFD",

  ink: "#171728",
  ink2: "#5C5C72",
  ink3: "#8E8EA3",

  line: "#E7E4F0",
  lineSoft: "#EFEDF5",
  card: "#FFFFFF",

  red: "#C8384C",
  redBg: "#FCEBEE",
  green: "#0F8A63",
  greenBg: "#E3F4ED",
  amber: "#A9700B",
  amberBg: "#FAF0DC",

  bgBase: "#F7F6FB",
} as const;

export const radius = {
  sm: "6px",
  ctl: "10px",
  card: "16px",
  pill: "999px",
} as const;

export const shadow = {
  flat: "0 1px 2px rgba(23, 23, 40, 0.05)",
  default: "0 1px 2px rgba(23, 23, 40, 0.04), 0 6px 20px rgba(23, 23, 40, 0.045)",
  raised: "0 1px 2px rgba(23, 23, 40, 0.05), 0 16px 44px rgba(23, 23, 40, 0.085)",
} as const;

export const motion = {
  fast: "0.13s",
  base: "0.2s",
  slow: "0.4s",
  ease: "cubic-bezier(0.22, 0.61, 0.36, 1)",
} as const;

/** SIX sizes only. Weight and colour carry hierarchy — never a seventh size. */
export const fontSize = {
  xs: "11px",
  sm: "12.5px",
  md: "14px",
  lg: "17px",
  xl: "22px",
  "2xl": "28px",
} as const;

export const font = {
  ui: '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  mono: '"JetBrains Mono", ui-monospace, Menlo, monospace',
} as const;

/**
 * Page background: two violet radials on a near-white base — NOT a
 * violet-to-peach linear gradient. Pair with `background-attachment: fixed`.
 */
export const pageBackground =
  "radial-gradient(1100px 620px at 18% -12%, #E6E2F8 0%, rgba(230, 226, 248, 0) 62%), " +
  "radial-gradient(900px 500px at 92% 6%, #EFEBF9 0%, rgba(239, 235, 249, 0) 58%), " +
  "#F7F6FB";

/**
 * Where gradients are allowed — exactly three. Anything else is flat.
 * Exported so a lint/review step can reference the canonical list.
 */
export const GRADIENT_ALLOWLIST = ["score-ring", "primary-button", "selection-spine"] as const;

export const tokens = { color, radius, shadow, motion, fontSize, font, pageBackground } as const;
export type Tokens = typeof tokens;
