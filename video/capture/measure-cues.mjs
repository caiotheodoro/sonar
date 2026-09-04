/**
 * Measures each narration cue against public/narration.mp3.
 *
 * The voice was generated as one take with a pause between cues, so the mp3's
 * speech segments (ffmpeg silencedetect) are the cues, in order. The count
 * must match exactly: N cues, N segments — otherwise both lists are printed
 * and nothing is written. Times are mp3-relative; storyboard.json places the
 * mp3 on the video timeline.
 *
 * Usage: node capture/measure-cues.mjs [--db -38] [--min-silence 450]
 */
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const VIDEO = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const NARRATION = join(VIDEO, "src", "data", "narration.json");
const MP3 = join(VIDEO, "public", "narration.mp3");

const arg = (name, dflt) => {
  const i = process.argv.indexOf(name);
  return i >= 0 ? Number(process.argv[i + 1]) : dflt;
};
const noiseDb = arg("--db", -38);
const minSilenceMs = arg("--min-silence", 450);

const durationMs = Math.round(
  Number(execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", MP3]).toString().trim()) * 1000,
);

const probe = spawnSync("ffmpeg", ["-i", MP3, "-af", `silencedetect=noise=${noiseDb}dB:d=${minSilenceMs / 1000}`, "-f", "null", "-"], { encoding: "utf8" });
const log = probe.stderr ?? "";
const silences = [];
let open = null;
for (const line of log.split("\n")) {
  const s = /silence_start:\s*([\d.]+)/.exec(line);
  const e = /silence_end:\s*([\d.]+)/.exec(line);
  if (s) open = Math.round(Number(s[1]) * 1000);
  if (e && open !== null) {
    silences.push([open, Math.round(Number(e[1]) * 1000)]);
    open = null;
  }
}
if (open !== null) silences.push([open, durationMs]);

// speech segments = the gaps between silences
const segments = [];
let cursor = 0;
for (const [s, e] of silences) {
  if (s - cursor > 150) segments.push([cursor, s]);
  cursor = e;
}
if (durationMs - cursor > 150) segments.push([cursor, durationMs]);

const file = JSON.parse(readFileSync(NARRATION, "utf8"));
const cues = file.narration;
console.log(`${MP3}: ${durationMs} ms, ${silences.length} silence(s) ≥ ${minSilenceMs} ms below ${noiseDb} dB, ${segments.length} speech segment(s); ${cues.length} cue(s)`);

/**
 * More segments than cues: the voice paused inside a cue as long as the
 * break between cues. Group the segments into N contiguous runs whose
 * speech time best matches each cue's share of the text (characters), by
 * dynamic programming — deterministic, and printed so the mapping is
 * inspectable. Fewer segments than cues is a real failure.
 */
let groups = segments.map((seg) => [seg]);
let method = `silencedetect noise=${noiseDb}dB d=${minSilenceMs}ms`;
if (segments.length > cues.length) {
  const chars = cues.map((c) => (c.spoken ?? c.text).length);
  const totalChars = chars.reduce((a, b) => a + b, 0);
  const speech = segments.reduce((a, [s, e]) => a + (e - s), 0);
  const expected = chars.map((n) => (n / totalChars) * speech);
  const M = segments.length;
  const N = cues.length;
  const cost = (i, j, k) => {
    const dur = segments.slice(i, j).reduce((a, [s, e]) => a + (e - s), 0);
    return Math.abs(dur - expected[k]);
  };
  const best = Array.from({ length: N + 1 }, () => new Array(M + 1).fill(Infinity));
  const back = Array.from({ length: N + 1 }, () => new Array(M + 1).fill(-1));
  best[0][0] = 0;
  for (let k = 1; k <= N; k++) {
    for (let j = k; j <= M; j++) {
      for (let i = k - 1; i < j; i++) {
        const c = best[k - 1][i] + cost(i, j, k - 1);
        if (c < best[k][j]) {
          best[k][j] = c;
          back[k][j] = i;
        }
      }
    }
  }
  const bounds = [];
  let j = M;
  for (let k = N; k >= 1; k--) {
    bounds.unshift([back[k][j], j]);
    j = back[k][j];
  }
  groups = bounds.map(([i, jj]) => segments.slice(i, jj));
  method += `; ${M} segments merged into ${N} cues by dp on character share (total error ${Math.round(best[N][M])} ms)`;
  console.log(`  merged ${M} segments into ${N} cues (${groups.map((g) => g.length).join("+")})`);
}
if (groups.length !== cues.length) {
  console.error("\ncount mismatch — nothing written. Segments:");
  segments.forEach(([s, e], i) => console.error(`  ${String(i + 1).padStart(2)}  ${s}–${e} ms (${e - s})`));
  console.error("Cues:");
  cues.forEach((c, i) => console.error(`  ${String(i + 1).padStart(2)}  ${c.id}  ${c.text.slice(0, 60)}`));
  console.error("\nTune --db / --min-silence, or regenerate with clearer <break/> tags.");
  process.exit(1);
}
const merged = groups.map((g) => [g[0][0], g[g.length - 1][1]]);
cues.forEach((c, i) => {
  c.startMs = merged[i][0];
  c.endMs = merged[i][1];
});
file.measured = {
  mp3Sha256: createHash("sha256").update(readFileSync(MP3)).digest("hex"),
  durationMs,
  method,
  measuredAt: new Date().toISOString().slice(0, 10),
};
writeFileSync(NARRATION, `${JSON.stringify(file, null, 2)}\n`);
cues.forEach((c) => console.log(`  ${c.id.padEnd(3)} ${String(c.startMs).padStart(6)}–${String(c.endMs).padStart(6)}  ${c.text.slice(0, 70)}`));
console.log("written: src/data/narration.json");
