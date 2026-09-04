/**
 * Shared geometry, so a shape can survive a hard cut.
 *
 * The cut has no dissolves. Continuity comes from drawing the same shape at
 * the same place on both sides of a cut: the band the dots settle into is the
 * band that splits, the rows the fan lands on are the rows that grow prices.
 * Every position both sides need lives here, once.
 */
import { LAYOUT } from "../theme";

export const STAGE = { w: 1920, h: 1080 } as const;

/** The rule the opening plate leaves behind; every act-A shot sits on it. */
export const RULE = { x: LAYOUT.margin, y: 946, w: STAGE.w - LAYOUT.margin * 2 } as const;

/** The mention band: dots stream into it, it splits, it becomes bars. */
export const BAND = { x: LAYOUT.margin, y: 500, w: STAGE.w - LAYOUT.margin * 2, h: 200 } as const;

/** One mention. */
export const DOT = { size: 22, gap: 10 } as const;

/** Rows for the Monid fan, the endpoint list and the per-call ledger. */
export const ROW = { x: 620, y0: 206, h: 58, w: 1236 } as const;

/** Where the fan starts: the one key, one balance. */
export const KEY = { x: LAYOUT.margin + 40, y: 530 } as const;

/** The price column act A ends on, and the wipe KILLED grows out of. */
export const COLUMN = { x: LAYOUT.margin, w: 300, baseY: RULE.y } as const;

/** Dots per row when a count is laid out inside BAND. */
export const perRow = Math.floor(BAND.w / (DOT.size + DOT.gap));

/** Grid position of the i-th dot inside BAND. */
export const dotAt = (i: number): { x: number; y: number } => ({
  x: BAND.x + (i % perRow) * (DOT.size + DOT.gap),
  y: BAND.y + Math.floor(i / perRow) * (DOT.size + DOT.gap),
});

/** Lanes the band splits into: same columns, stacked blocks. */
export const LANE = { h: 2 * (DOT.size + DOT.gap), gap: 78 } as const;

/** Position of the n-th dot of a lane, in the lane's own block. */
export const laneDot = (n: number, lane: number): { x: number; y: number } => ({
  x: BAND.x + (n % perRow) * (DOT.size + DOT.gap),
  y: BAND.y + lane * (LANE.h + LANE.gap) + Math.floor(n / perRow) * (DOT.size + DOT.gap),
});

/** Ease used by every carry: fast out, settle. */
export const ease = (p: number): number => 1 - Math.pow(1 - Math.max(0, Math.min(1, p)), 3);
