/**
 * The resolved cut. Evaluated once at import; a storyboard that does not
 * resolve fails the bundle before a frame is drawn.
 */
import storyboardRaw from "../data/storyboard.json";
import narrationRaw from "../data/narration.json";
import beatGridRaw from "../data/beat-grid.json";
import { FPS } from "../manifest";
import { msToFrame as msToFrameRaw, resolveTimeline } from "./resolve.mjs";
import type { Act, BeatGrid, Cue, NarrationFile, Storyboard, Timeline } from "./types";

export const STORYBOARD = storyboardRaw as unknown as Storyboard;
export const NARRATION = narrationRaw as unknown as NarrationFile;
export const BEAT_GRID = beatGridRaw as unknown as BeatGrid;
export const CUES: Cue[] = NARRATION.narration;

export const TIMELINE: Timeline = resolveTimeline({
  storyboard: STORYBOARD,
  cues: CUES,
  grid: BEAT_GRID,
  fps: FPS,
});

export const msToFrame = (ms: number): number => msToFrameRaw(ms, FPS);

/** First frame of an act. */
export const actFrom = (act: Act): number => TIMELINE.acts[act].from;

/** Frames (video-absolute) of a cue's start. Throws if unmeasured. */
export const cueFrame = (id: string, edge: "start" | "end" = "start"): number => {
  const cue = TIMELINE.cues.find((c) => c.id === id);
  if (!cue) throw new Error(`no cue "${id}" in narration.json`);
  if (!TIMELINE.narrationMeasured) throw new Error(`cue "${id}" asked for but the narration is unmeasured`);
  return edge === "end" ? cue.to : cue.from;
};
