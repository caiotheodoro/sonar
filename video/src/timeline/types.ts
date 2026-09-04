/** The cut, as data. See src/data/storyboard.json and resolve.mjs. */

export type Act = "brand24" | "killed" | "monid" | "rebuild" | "receipt" | "honest" | "outro";

export type Anchor =
  | { ms: number }
  | { beat: number; offsetMs?: number }
  | { hit: number; offsetMs?: number }
  | { cue: string; edge?: "start" | "end"; offsetMs?: number };

export type Move = "hold" | "push" | "pan-down" | "zoom" | "punch";

export type ReceiptRowId =
  | "runs"
  | "billed"
  | "zero"
  | "failed"
  | "verdict"
  | "monid"
  | "llm"
  | "voice"
  | "total"
  | "monthly"
  | "mentions";

interface ShotBase {
  id: string;
  act: Act;
  start: Anchor;
  /** Only the last shot carries an end; every other shot ends where the next starts. */
  end?: Anchor;
  /** Snap the resolved start to the nearest beat or hit when within tolerance. */
  snap?: "beat" | "hit";
  /** Hide the frame-locked status strip on this shot. */
  statusStrip?: boolean;
  /** Per-shot sound overrides: `cut: false` silences the cut tick. */
  sfx?: { cut?: boolean };
}

export interface Crop {
  x: number;
  y: number;
  w: number;
  h: number;
}

export type ShotSpec =
  | {
      kind: "shot";
      src: string;
      crop?: Crop;
      move?: Move;
      /** External fact ids rendered as chips on this specimen. */
      facts?: string[];
      /** Plate line under the specimen: slash-separated segments. Data-free text only. */
      plate?: string[];
      /** Highlight rectangle in source px (the Team tier, say). */
      highlight?: Crop;
      /** Point in source px the zoom or punch moves toward. */
      focus?: { x: number; y: number };
      /** zoom: [from, to] scale over the shot; punch: the scale after `at`. */
      zoom?: [number, number] | number;
      /** punch: shot-local frame of the cut-in. */
      at?: number;
      /** One-frame plate flash on the first frame, with a shutter (photo burst). */
      flash?: boolean;
    }
  | {
      kind: "stamp";
      text: string;
      variant: "killed" | "title" | "ratio" | "outro" | "plate";
      plate?: string[];
    }
  | { kind: "card"; card: string }
  | {
      kind: "cast";
      src: "run_trace" | "ask" | "empty_run";
      speed?: number;
      rows?: number;
      /** Cast-clock milliseconds already elapsed when the shot opens. */
      castFromMs?: number;
    }
  | { kind: "receipt"; rows: ReceiptRowId[]; results?: "demo" | "demo-empty" };

export type Shot = ShotBase & ShotSpec;

export interface Storyboard {
  _comment?: string;
  targetMs: number;
  capMs: number;
  minShotMs: number;
  snapToleranceMs: number;
  music: {
    src: string;
    volume: number;
    duckTo: number;
    duckMs: number;
    fadeOutMs: number;
  };
  narration: { src: string; offsetMs: number };
  sfx?: { volume: number };
  acts: Act[];
  shots: Shot[];
}

export interface Cue {
  id: string;
  act: Act;
  text: string;
  spoken?: string;
  /** Relative to public/narration.mp3, measured by capture/measure-cues.mjs. */
  startMs: number;
  endMs: number;
}

export interface NarrationFile {
  _comment?: string;
  voice: Record<string, unknown>;
  measured: { mp3Sha256: string | null; durationMs: number; method: string };
  narration: Cue[];
}

export interface BeatGrid {
  bpm: number;
  beatOffsetMs: number;
  durationMs: number;
  trackSha256: string;
  beatsMs: number[];
  hitsMs: number[];
}

export interface ResolvedShot {
  shot: Shot;
  index: number;
  startMs: number;
  endMs: number;
  from: number;
  durationInFrames: number;
  /** Set when a snap moved the start; the distance moved, ms. */
  snappedMs?: number;
}

export interface ResolvedCue extends Cue {
  /** On the video timeline, ms. */
  videoStartMs: number;
  videoEndMs: number;
  from: number;
  to: number;
  /** Shot ids this cue overlaps. */
  shots: string[];
}

export interface Timeline {
  shots: ResolvedShot[];
  cues: ResolvedCue[];
  totalMs: number;
  totalFrames: number;
  acts: Record<Act, { from: number; to: number; startMs: number; endMs: number }>;
  narrationFrom: number;
  narrationMeasured: boolean;
  beatFrames: number[];
  hitFrames: number[];
}
