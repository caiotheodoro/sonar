/**
 * Design tokens for the sonar hackathon video — dark instrument system.
 *
 * Literals, not CSS variables: `var(--color-…)` does not resolve inside a
 * headless Remotion bundle where SVG attributes and canvas measurement need
 * concrete values.
 *
 * One reading colour (`accent`, sodium amber) for every *measured* value, the
 * read-line, the live trace, citation markers. `abstain` is a calm grey for the
 * em-dash that stands in for a number sonar refused to guess — never red, an
 * abstention is not an error.
 */
export const T = {
  text: "#E6E8EA",
  textMuted: "#9BA1A8",
  textFaint: "#5B6169",
  accent: "#F2A83B",
  accentPress: "#D8901F",
  abstain: "#5B6169",
  bg: "#08090A",
  bgSubtle: "#0E1011",
  codeBg: "#0E1011",
  border: "#1C1F22",
  borderStrong: "#2A2E33",
  /** captions and labels — sentence case, no tracking; mono is the vernacular */
  font: '"Space Grotesk", system-ui, sans-serif',
  /** everything structural + the big display figures + the terminal, one face */
  mono: '"Geist Mono", ui-monospace, monospace',
} as const;

/**
 * Categorical order: brand first, then competitors in query order. On the dark
 * ground the brand keeps the amber; the rivals step down in grey. Every series
 * still carries a direct value label — colour is never the only encoding.
 */
export const SERIES = ["#F2A83B", "#9BA1A8", "#6E747C", "#3A3F45"] as const;

/** Neutral for reference marks that carry no identity (the incumbent price). */
export const NEUTRAL = "#5B6169";

/**
 * Verdict rendering. RECONCILED is confident plain text on this ground, not a
 * green badge; PARTIAL / REPLAY keep a muted hue so a bad verdict still reads.
 */
export const VERDICT = {
  RECONCILED: "#E6E8EA",
  PARTIAL: "#C77B5A",
  REPLAY: "#B08CCF",
} as const;

/** Sentiment label colours — warm, not alarm. */
export const SENTIMENT = {
  pos: "#7FB88C",
  neg: "#C77B5A",
  neu: "#5B6169",
} as const;

export const GRID = { stroke: T.border, dasharray: "2 6" } as const;

/** Snappy ease-out; everything moves fast and settles. Frames at 30fps. */
export const MOTION = {
  easeOut: [0.22, 1, 0.36, 1] as const,
  snap: [0.22, 1, 0.36, 1] as const,
  fadeFrames: 9,
  staggerFrames: 2,
};
