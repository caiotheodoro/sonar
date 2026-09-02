/**
 * Design tokens for the sonar hackathon video.
 *
 * Same system as the author's site and the assay video: literals rather than
 * CSS variables, because `var(--color-…)` does not resolve inside a headless
 * Remotion bundle where SVG attributes and canvas measurement need concrete
 * values.
 */
export const T = {
  text: "#171717",
  textMuted: "#6b6b6b",
  textFaint: "#a3a3a3",
  accent: "#c93d1e",
  accentPress: "#a83218",
  bg: "#ffffff",
  bgSubtle: "#f8f8f7",
  codeBg: "#f3f3ed",
  border: "#e8e8e4",
  borderStrong: "#d4d4cf",
  font: '"Plus Jakarta Sans", system-ui, sans-serif',
  mono: '"Geist Mono", ui-monospace, monospace',
} as const;

/**
 * Categorical series colours, validated against the light surface. The worst
 * colour-vision pair sits in the band that is only legal with a secondary
 * encoding, so every series carries a direct value label, never colour alone.
 * Assign in fixed order: brand first, then competitors in query order.
 */
export const SERIES = ["#c93d1e", "#4361ee", "#1f7a3d", "#9a6700"] as const;

/** Neutral for reference marks that carry no identity: the incumbent price. */
export const NEUTRAL = "#a3a3a3";

/**
 * Receipt verdict colours. RECONCILED is the only verdict `sonar verify`
 * accepts; PARTIAL means a run is still unreconciled; REPLAY means the receipt
 * was produced from stored artifacts and spent nothing.
 */
export const VERDICT = {
  RECONCILED: "#1a7f37",
  PARTIAL: "#9a6700",
  REPLAY: "#8250df",
} as const;

/** Sentiment label colours, used only beside the label word. */
export const SENTIMENT = {
  pos: "#1a7f37",
  neg: "#cf222e",
  neu: "#6e7781",
} as const;

export const GRID = { stroke: T.border, dasharray: "2 4" } as const;

/** fadeUp from the site's animations.css, as frames at 30fps. */
export const MOTION = {
  easeOut: [0.25, 0.46, 0.45, 0.94] as const,
  fadeFrames: 17,
  staggerFrames: 2,
};
