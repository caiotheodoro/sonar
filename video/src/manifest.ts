/**
 * The video, as data.
 *
 * Copy edits and retiming happen HERE, never inside a scene component. Scenes
 * read their beat from this file and own no timing of their own.
 *
 * The hackathon rules that bind this cut: sixty to ninety seconds, the first
 * five seconds show what died, the incumbent price beside the measured cost on
 * screen, a visible Monid call, captions, 1080p, `#monid` in the outro. The
 * scene durations below are the storyboard's targets and sum to under ninety
 * seconds; `TOTAL_FRAMES` is derived from them, never typed.
 *
 * Every number on screen comes from the frozen demo run through `RESULTS`.
 * The three files are imported by alias so a tree without them still
 * type-checks, while bundling and rendering fail (see `remotion.config.ts`
 * and `src/results.d.ts`).
 */
import receiptRaw from "@results/receipt.json";
import statsRaw from "@results/stats.json";
import digestRaw from "@results/digest.json";
import receiptEmptyRaw from "@results-empty/receipt.json";
import statsEmptyRaw from "@results-empty/stats.json";
import digestEmptyRaw from "@results-empty/digest.json";
import narrationFile from "./data/narration.json";
import { loadResultsFrom } from "./data/results";

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;

/** The demo run, validated field by field. Throws at import when a cited number is absent. */
export const RESULTS = loadResultsFrom("demo", {
  receipt: receiptRaw,
  stats: statsRaw,
  digest: digestRaw,
});

/** The zero-mention run (Zephyrium Bank): a receipt reconciles with nothing to find. */
export const RESULTS_EMPTY = loadResultsFrom("demo-empty", {
  receipt: receiptEmptyRaw,
  stats: statsEmptyRaw,
  digest: digestEmptyRaw,
});

export interface CaptionCue {
  /** Scene id this cue belongs to; used to derive sub-beat frames. */
  scene: string;
  /** Milliseconds from the start of the video. */
  startMs: number;
  endMs: number;
  text: string;
  /** Voice-only override for `text`, where an identifier must not be read literally. */
  spoken?: string;
}

interface NarrationFile {
  _comment: string;
  narration: CaptionCue[];
}

/** Every caption cue, in order. Empty until the narration lands. */
export const captions: CaptionCue[] = (narrationFile as NarrationFile).narration;

export interface Cast {
  /** File under public/casts, recorded by capture/record-casts.mjs. */
  src: string;
  /** Playback multiplier; a ramp drops no frames, so no run is ever cut. */
  speed?: number;
  /** Frames into the scene to start the replay. */
  startFrame?: number;
  /** Terminal grid rows to show. */
  rows?: number;
  /** Terminal glyph size, px. */
  fontSize?: number;
}

export type SceneId =
  | "price-died"
  | "live-trace"
  | "receipt"
  | "ask"
  | "empty-run"
  | "outro";

export interface Scene {
  id: SceneId;
  /** Storyboard line, the claim this beat makes. Never a number. */
  claim: string;
  durationInFrames: number;
  cast?: Cast;
}

const seconds = (s: number): number => s * FPS;

const SCENE_IDS: SceneId[] = ["price-died", "live-trace", "receipt", "ask", "empty-run", "outro"];

/** Storyboard targets (README.md), used only until the narration is timed. */
const TARGET_SECONDS: Record<SceneId, number> = {
  "price-died": 5,
  "live-trace": 12,
  receipt: 12,
  ask: 18,
  "empty-run": 11,
  outro: 6,
};

/** Silence after the last cue, so the outro's replayed read-lines have room to land. */
const OUTRO_TAIL_MS = 5000;

/**
 * Scene durations, one per `SCENE_IDS` entry, derived from the timed
 * narration rather than typed: each boundary sits at the midpoint of the
 * gap between the previous scene's last cue and this scene's first, so a
 * re-timed narration.json reflows the cut instead of silently drifting out
 * of sync with it. Before the narration is measured (`startMs`/`endMs` all
 * 0), falls back to the storyboard targets above.
 */
const sceneDurationsFrames = (): number[] => {
  const timed = captions.some((c) => c.endMs > 0);
  if (!timed) return SCENE_IDS.map((id) => seconds(TARGET_SECONDS[id]));

  const bounds = SCENE_IDS.map((id) => {
    const cues = captions.filter((c) => c.scene === id);
    if (cues.length === 0) {
      throw new Error(`src/data/narration.json: no cues for scene "${id}"`);
    }
    return {
      start: Math.min(...cues.map((c) => c.startMs)),
      end: Math.max(...cues.map((c) => c.endMs)),
    };
  });
  const starts = bounds.map((b, i) => (i === 0 ? 0 : Math.round((bounds[i - 1].end + b.start) / 2)));
  const totalMs = bounds[bounds.length - 1].end + OUTRO_TAIL_MS;
  const frameBounds = [...starts, totalMs].map((ms) => Math.round((ms / 1000) * FPS));
  return frameBounds.slice(1).map((f, i) => f - frameBounds[i]);
};

const durations = sceneDurationsFrames();

/**
 * The six beats. Durations come from `sceneDurationsFrames`, above.
 */
export const scenes: Scene[] = [
  {
    id: "price-died",
    claim: "The incumbent's monthly price beside the receipt's measured cost.",
    durationInFrames: durations[0],
  },
  {
    id: "live-trace",
    claim: "A live POST /v1/run, as sonar run --trace prints it.",
    durationInFrames: durations[1],
    cast: { src: "run_trace", speed: 1.8, rows: 20 },
  },
  {
    id: "receipt",
    claim: "The receipt itemises every run, every zero, the verdict.",
    durationInFrames: durations[2],
  },
  {
    id: "ask",
    claim: "sonar reports what it can, abstains from what it can't, then answers with citations.",
    durationInFrames: durations[3],
    cast: { src: "ask", speed: 1.6, rows: 14 },
  },
  {
    id: "empty-run",
    claim: "A brand with nothing to find still gets a receipt; every estimate abstains.",
    durationInFrames: durations[4],
    cast: { src: "empty_run", speed: 1.8, rows: 16 },
  },
  {
    id: "outro",
    claim: "The repository, the hashtag, the price that died.",
    durationInFrames: durations[5],
  },
];

/** Frame offset of scene `i`, as a prefix sum. */
export const from = (index: number): number =>
  scenes.slice(0, index).reduce((acc, s) => acc + s.durationInFrames, 0);

export const TOTAL_FRAMES = scenes.reduce((acc, s) => acc + s.durationInFrames, 0);

/** The hackathon cap, in frames. Checked at import so a long cut cannot slip through. */
export const MAX_FRAMES = seconds(90);
if (TOTAL_FRAMES > MAX_FRAMES) {
  throw new Error(
    `the storyboard runs ${TOTAL_FRAMES} frames, over the ${MAX_FRAMES}-frame hackathon cap`,
  );
}

/**
 * The scene-local frame at which the `index`-th cue of `sceneId` starts.
 * Scenes run inside a `<Sequence from={from(i)})>`, which rebases
 * `useCurrentFrame()` to 0 at the scene's own start; a scene's own
 * animations key off this, in cue order, rather than a typed offset, so
 * a re-timed narration reflows sub-beat timing along with the scene cut.
 */
export const cueFrame = (sceneId: SceneId, index: number): number => {
  const cues = captions.filter((c) => c.scene === sceneId);
  const cue = cues[index];
  if (!cue) throw new Error(`src/data/narration.json: scene "${sceneId}" has no cue ${index}`);
  const sceneIndex = scenes.findIndex((s) => s.id === sceneId);
  return Math.round((cue.startMs / 1000) * FPS) - from(sceneIndex);
};

/** Frames into the video at which the narration starts. */
export const voiceOffset = 15;

/** The narration mp3 under public/, produced by sonar's own TTS path. Null until it exists. */
export const narrationSrc: string | null = "narration.mp3";

export const musicSrc: string | null = "music.mp3";
export const musicVolume = 0.22;

export const PUBLISHED = {
  code: "github.com/caiotheodoro/sonar",
  hashtag: "#monid",
} as const;
