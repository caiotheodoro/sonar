/**
 * Sub-beat boundaries, derived from the narration rather than guessed.
 *
 * Cues in `narration.json` carry absolute `startMs` values written by
 * capture/retime-captions.mjs from the real mp3. A scene asks for its cues and
 * gets them in its own frame space, so a sub-beat drawn at "the cue that says
 * the price" follows the voice if the voice is re-recorded.
 */
import { FPS, captions, from, scenes } from "./manifest";
import type { CaptionCue, SceneId } from "./manifest";

const toFrame = (ms: number): number => Math.round((ms / 1000) * FPS);

/** Cues for one scene, with `startMs`/`endMs` shifted to scene-relative milliseconds. */
export const cuesFor = (scene: SceneId): CaptionCue[] => {
  const index = scenes.findIndex((s) => s.id === scene);
  if (index < 0) throw new Error(`no scene "${scene}" in the manifest`);
  const offsetMs = (from(index) / FPS) * 1000;
  return captions
    .filter((c) => c.scene === scene)
    .map((c) => ({ ...c, startMs: c.startMs - offsetMs, endMs: c.endMs - offsetMs }));
};

/**
 * Frame, within the scene, at which the i-th cue of that scene starts.
 * Throws when the narration has not been timed, so a sub-beat can never
 * silently collapse to frame zero.
 */
export const cueFrame = (scene: SceneId, index: number): number => {
  const cues = cuesFor(scene);
  const cue = cues[index];
  if (!cue) throw new Error(`scene "${scene}" has no cue ${index}; ${cues.length} cue(s) exist`);
  if (cues.every((c) => c.startMs === 0 && c.endMs === 0)) {
    throw new Error(
      `narration for "${scene}" has not been timed. Run node capture/retime-captions.mjs`,
    );
  }
  return toFrame(cue.startMs);
};

/** Frame, within the scene, at which its narration finishes. Zero when there is none. */
export const narrationEnd = (scene: SceneId): number => {
  const cues = cuesFor(scene);
  const last = cues[cues.length - 1];
  return last ? toFrame(last.endMs) : 0;
};
