import type { BeatGrid, Cue, Storyboard, Timeline } from "./types";

export function msToFrame(ms: number, fps: number): number;
export function resolveTimeline(input: {
  storyboard: Storyboard;
  cues: Cue[];
  grid: BeatGrid;
  fps: number;
  narrationMeasured?: boolean;
}): Timeline;
export function timelineReport(t: Timeline): string;
export function timelineSrt(t: Timeline): string;
