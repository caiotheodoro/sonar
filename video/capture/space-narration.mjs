/**
 * Places the holds.
 *
 * The take from the ElevenLabs web UI has one even break between lines, which
 * makes the voice read as one long paragraph: nothing is ever held, and the
 * stamps land while it is still talking. This cuts the take at those breaks
 * and rebuilds it with the holds `spacing` asks for — long where a stamp or a
 * sequence should play on music alone, short inside an act — then writes the
 * cue times it just built, so nothing has to be measured back out.
 *
 * public/narration.raw.mp3 (the take, tracked) -> public/narration.mp3
 *
 * Usage: node capture/space-narration.mjs [--db -38] [--min-silence 500]
 */
import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const VIDEO = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const NARRATION = join(VIDEO, "src", "data", "narration.json");
const RAW = join(VIDEO, "public", "narration.raw.mp3");
const OUT = join(VIDEO, "public", "narration.mp3");

const arg = (name, dflt) => {
  const i = process.argv.indexOf(name);
  return i >= 0 ? Number(process.argv[i + 1]) : dflt;
};
const noiseDb = arg("--db", -38);
const minSilenceMs = arg("--min-silence", 500);

const ffprobeMs = (file) =>
  Math.round(Number(execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", file]).toString().trim()) * 1000);

const detect = (file) => {
  // ffmpeg reports silencedetect on stderr and exits 0, so read stderr either way.
  const run = spawnSync("ffmpeg", ["-i", file, "-af", `silencedetect=noise=${noiseDb}dB:d=${minSilenceMs / 1000}`, "-f", "null", "-"], { encoding: "utf8" });
  const log = run.stderr ?? "";
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
  const duration = ffprobeMs(file);
  if (open !== null) silences.push([open, duration]);
  const segments = [];
  let cursor = 0;
  for (const [s, e] of silences) {
    if (s - cursor > 150) segments.push([cursor, s]);
    cursor = e;
  }
  if (duration - cursor > 150) segments.push([cursor, duration]);
  return { segments, duration };
};

const file = JSON.parse(readFileSync(NARRATION, "utf8"));
const cues = file.narration;
const { leadMs, gapsMs, tailMs } = file.spacing;
if (gapsMs.length !== cues.length - 1) {
  console.error(`spacing.gapsMs has ${gapsMs.length} holds for ${cues.length} cues; it needs ${cues.length - 1}`);
  process.exit(1);
}

const { segments, duration } = detect(RAW);
console.log(`${RAW}: ${duration} ms, ${segments.length} speech segment(s) for ${cues.length} cue(s)`);

// More segments than cues: the voice paused inside a line as long as between
// them. Merge neighbours into N runs by character share, the same rule the
// measurer uses, and print the grouping so it can be checked.
let groups = segments.map((s) => [s]);
if (segments.length > cues.length) {
  const chars = cues.map((c) => (c.spoken ?? c.text).length);
  const totalChars = chars.reduce((a, b) => a + b, 0);
  const speech = segments.reduce((a, [s, e]) => a + (e - s), 0);
  const want = chars.map((n) => (n / totalChars) * speech);
  const M = segments.length;
  const N = cues.length;
  const best = Array.from({ length: N + 1 }, () => new Array(M + 1).fill(Infinity));
  const back = Array.from({ length: N + 1 }, () => new Array(M + 1).fill(-1));
  best[0][0] = 0;
  const span = (i, j) => segments.slice(i, j).reduce((a, [s, e]) => a + (e - s), 0);
  for (let k = 1; k <= N; k++) {
    for (let j = k; j <= M; j++) {
      for (let i = k - 1; i < j; i++) {
        const c = best[k - 1][i] + Math.abs(span(i, j) - want[k - 1]);
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
  console.log(`  merged ${M} segments into ${N} cues (${groups.map((g) => g.length).join("+")})`);
}
if (groups.length !== cues.length) {
  console.error("could not line the take up with the cues; tune --db / --min-silence");
  process.exit(1);
}

// Cut each line out of the take, pad the head and tail a little so no
// consonant is clipped, then lay them out against the holds.
const PAD = 90;
const tmp = mkdtempSync(join(tmpdir(), "sonar-narration-"));
const parts = [];
let at = leadMs;
groups.forEach((g, i) => {
  const from = Math.max(0, g[0][0] - PAD);
  const to = Math.min(duration, g[g.length - 1][1] + PAD);
  const part = join(tmp, `${String(i).padStart(2, "0")}.wav`);
  execFileSync("ffmpeg", ["-v", "error", "-y", "-i", RAW, "-ss", String(from / 1000), "-to", String(to / 1000), "-ar", "44100", "-ac", "1", part]);
  const len = to - from;
  parts.push({ part, at, len });
  cues[i].startMs = at + PAD;
  cues[i].endMs = at + len - PAD;
  at += len + (gapsMs[i] ?? 0);
});
const totalMs = at - (gapsMs[gapsMs.length - 1] ?? 0) + tailMs;

const inputs = parts.flatMap((p) => ["-i", p.part]);
const delays = parts.map((p, i) => `[${i}:a]adelay=${p.at}|${p.at}[a${i}]`).join(";");
const mix = `${parts.map((_, i) => `[a${i}]`).join("")}amix=inputs=${parts.length}:normalize=0,apad=whole_dur=${totalMs / 1000}[out]`;
execFileSync("ffmpeg", ["-v", "error", "-y", ...inputs, "-filter_complex", `${delays};${mix}`, "-map", "[out]", "-ar", "44100", "-b:a", "160k", OUT]);
rmSync(tmp, { recursive: true, force: true });

file.measured = {
  mp3Sha256: createHash("sha256").update(readFileSync(OUT)).digest("hex"),
  durationMs: ffprobeMs(OUT),
  method: `capture/space-narration.mjs from narration.raw.mp3 (silencedetect noise=${noiseDb}dB d=${minSilenceMs}ms), holds from spacing.gapsMs`,
  measuredAt: new Date().toISOString().slice(0, 10),
  rawSha256: createHash("sha256").update(readFileSync(RAW)).digest("hex"),
};
writeFileSync(NARRATION, `${JSON.stringify(file, null, 2)}\n`);
cues.forEach((c, i) => console.log(`  ${c.id.padEnd(3)} ${String(c.startMs).padStart(6)}–${String(c.endMs).padStart(6)}  hold after ${String(gapsMs[i] ?? 0).padStart(5)}  ${c.text.slice(0, 52)}`));
console.log(`written: public/narration.mp3 (${file.measured.durationMs} ms) and src/data/narration.json`);
