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
import narrationFile from "./data/narration.json";
import { loadResults } from "./data/results";

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;

/** The demo run, validated field by field. Throws at import when a cited number is absent. */
export const RESULTS = loadResults({ receipt: receiptRaw, stats: statsRaw, digest: digestRaw });

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

export interface CastSegment {
  /** Frames into the cast to begin this segment. */
  trimBefore: number;
  /** Playback multiplier. A ramp drops no frames, so no run is ever cut. */
  playbackRate: number;
  /** How many frames of the scene this segment occupies. */
  sceneFrames: number;
}

export interface Cast {
  /** File under public/casts, recorded by capture/record-casts.mjs. */
  src: string;
  segments?: CastSegment[];
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

/**
 * The six beats. Durations are the storyboard targets from README.md; the
 * final cut trims them against the narration, never the other way round.
 */
export const scenes: Scene[] = [
  {
    id: "price-died",
    claim: "The incumbent's monthly price beside the receipt's measured cost.",
    durationInFrames: seconds(5),
  },
  {
    id: "live-trace",
    claim: "A live POST /v1/run, as sonar run --trace prints it.",
    durationInFrames: seconds(20),
    cast: { src: "run_trace" },
  },
  {
    id: "receipt",
    claim: "The receipt scrolls: every run, every zero, the verdict.",
    durationInFrames: seconds(15),
    cast: { src: "receipt" },
  },
  {
    id: "ask",
    claim: "sonar ask answers with citations that resolve to real mentions.",
    durationInFrames: seconds(18),
    cast: { src: "ask" },
  },
  {
    id: "empty-run",
    claim: "A brand with no mentions still gets a receipt, and no digest.",
    durationInFrames: seconds(12),
    cast: { src: "avenza_empty" },
  },
  {
    id: "outro",
    claim: "The repository, the hashtag, the price that died.",
    durationInFrames: seconds(8),
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

/** Frames into the video at which the narration starts. */
export const voiceOffset = 15;

/** The narration mp3 under public/, produced by sonar's own TTS path. Null until it exists. */
export const narrationSrc: string | null = null;

export const musicSrc: string | null = null;
export const musicVolume = 0.22;

export const PUBLISHED = {
  code: "github.com/caiotheodoro/sonar",
  hashtag: "#monid",
} as const;
