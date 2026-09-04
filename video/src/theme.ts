/**
 * Design tokens for the sonar video — the machine nameplate system.
 *
 * Literals, not CSS variables: `var(--color-…)` does not resolve inside a
 * headless Remotion bundle where SVG attributes and canvas measurement need
 * concrete values.
 *
 * True black ground, plate-white type, one signal orange that is spent in one
 * place: the KILLED act, the price figures, and the retract of an abstention.
 * Everything Monid and sonar is white on black — calm, machine. The interrupt
 * gets the colour so the interrupt is the thing you remember.
 */
export const T = {
  ink: "#000000",
  plate: "#EDEDE9",
  engrave: "#8A8A85",
  signal: "#FF4D00",
  shadow: "#141414",
  keyline: "#2A2A28",
  // back-compat aliases used by the retained components (ReadLine, TerminalCast, DataPanel)
  text: "#EDEDE9",
  textMuted: "#8A8A85",
  textFaint: "#5C5C58",
  accent: "#FF4D00",
  accentPress: "#D93F00",
  abstain: "#5C5C58",
  bg: "#000000",
  bgSubtle: "#0A0A0A",
  codeBg: "#0A0A0A",
  border: "#1E1E1C",
  borderStrong: "#2A2A28",
  /** plates, specs, figures, the terminal — one mono face */
  mono: '"Geist Mono", ui-monospace, monospace',
  /** stamps and act titles — condensed industrial display */
  display: '"Big Shoulders", "Big Shoulders", "Big Shoulders Display", "Archivo Narrow", Impact, sans-serif',
  /** alias kept for the retained components; there is no separate caption face any more */
  font: '"Geist Mono", ui-monospace, monospace',
} as const;

/** Brand first, then competitors in query order. Colour is never the only encoding. */
export const SERIES = ["#EDEDE9", "#8A8A85", "#5C5C58", "#3A3A38"] as const;

/** Neutral for reference marks that carry no identity (the incumbent price). */
export const NEUTRAL = "#5C5C58";

export const VERDICT = {
  RECONCILED: "#EDEDE9",
  PARTIAL: "#C77B5A",
  REPLAY: "#B08CCF",
} as const;

/** Sentiment, read as plate text, not alarm colours. */
export const SENTIMENT = {
  pos: "#EDEDE9",
  neg: "#8A8A85",
  neu: "#5C5C58",
} as const;

export const GRID = { stroke: T.border, dasharray: "2 6" } as const;

/**
 * Motion rules. Frames at 30fps. There are three gestures in the whole cut:
 * the scan (a screenshot revealed top-to-bottom by one orange line), the slam
 * (a stamp lands from 1.12× to 1× in four frames), and the count (a figure
 * runs up over ten frames). No fades, no slides.
 */
export const MOTION = {
  easeOut: [0.22, 1, 0.36, 1] as const,
  snap: [0.22, 1, 0.36, 1] as const,
  scanFrames: 8,
  slamFrames: 4,
  countFrames: 10,
  fadeFrames: 4,
  staggerFrames: 2,
};

/** Page geometry. */
export const LAYOUT = { margin: 64, grid: 8, specimenWidth: 1400 } as const;

/** Type scale, px. */
export const TYPE = {
  stamp: 420,
  headline: 160,
  title: 72,
  value: 44,
  label: 22,
} as const;
