/**
 * Retimes caption cues against the generated narration.
 *
 * Cue times in narration.json start as estimates. Once public/narration.mp3
 * exists its real duration is known, so cues are redistributed across it in
 * proportion to their character count: an approximation of speaking time, not
 * forced alignment. It gets the cues close; drift is visible on review and is
 * fixed by hand in narration.json.
 *
 * Times are absolute from the start of the video, offset by `voiceOffset`
 * frames from the manifest. One mp3, one timeline.
 *
 * Usage: node capture/retime-captions.mjs
 */
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const VIDEO = resolve(HERE, "..");
const NARRATION = join(VIDEO, "src", "data", "narration.json");
const MP3 = join(VIDEO, "public", "narration.mp3");

/** Frames per second and the narration's start frame, as src/manifest.ts declares them. */
const FPS = 30;
const VOICE_OFFSET_FRAMES = 15;
/** Milliseconds of silence between cues, and before the first one. */
const LEAD_MS = Math.round((VOICE_OFFSET_FRAMES / FPS) * 1000);
const GAP_MS = 140;
/** Words per minute assumed until a rate has been measured for the voice. */
const DEFAULT_WPM = 130;

const duration = (file) =>
  Math.round(
    Number(
      execFileSync("ffprobe", [
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        file,
      ]).toString().trim(),
    ) * 1000,
  );

const file = JSON.parse(readFileSync(NARRATION, "utf8"));
const cues = file.narration;
if (!Array.isArray(cues) || cues.length === 0) {
  console.log("narration.json has no cues yet; nothing to retime");
  process.exit(0);
}
const rates = JSON.parse(readFileSync(join(VIDEO, "src", "data", "voice-rates.json"), "utf8")).wpm;
const measuredRates = Object.values(rates);
const wpm = measuredRates.length
  ? measuredRates.reduce((a, b) => a + b, 0) / measuredRates.length
  : DEFAULT_WPM;

const words = cues.reduce((a, c) => a + (c.spoken ?? c.text).split(/\s+/).length, 0);
const measured = existsSync(MP3);
const total = measured ? duration(MP3) : Math.round((words / wpm) * 60 * 1000);
const weights = cues.map((c) => c.text.length);
const sum = weights.reduce((a, b) => a + b, 0);
const speakable = total - GAP_MS * (cues.length - 1);

let t = LEAD_MS;
cues.forEach((cue, i) => {
  const span = Math.round((weights[i] / sum) * speakable);
  cue.startMs = t;
  cue.endMs = t + span;
  t += span + GAP_MS;
});

console.log(
  `${measured ? "MEASURED" : "predicted"} ${cues.length} cues over ${(total / 1000).toFixed(1)}s ` +
    `(${words} words, ${Math.round(words / (total / 60000))} wpm)`,
);
writeFileSync(NARRATION, `${JSON.stringify(file, null, 2)}\n`);
