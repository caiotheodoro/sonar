/**
 * One still per cut, pulled from the rendered mp4 at each shot's first frame
 * (+1, so a premount blank would show) or, with --mid, twenty-four frames in
 * (so scans, counts and rows have landed), tiled into out/cuts.png.
 *
 * Usage: node capture/verify-cuts.mjs [out/sonar.mp4] [--mid]
 */
import { execFileSync } from "node:child_process";
import { mkdirSync, readdirSync, rmSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { loadTimeline } from "./resolve-timeline.mjs";

const VIDEO = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2).filter((a) => !a.startsWith("--"));
const MID = process.argv.includes("--mid");
const MP4 = resolve(VIDEO, args[0] ?? "out/sonar.mp4");
const DIR = join(VIDEO, "out", "cuts");
rmSync(DIR, { recursive: true, force: true });
mkdirSync(DIR, { recursive: true });

const t = loadTimeline();
for (const s of t.shots) {
  const offset = MID ? Math.min(24, s.durationInFrames - 2) : 1;
  const at = ((s.from + offset) / 30).toFixed(3);
  const file = join(DIR, `${String(s.index + 1).padStart(2, "0")}-${s.shot.id}.png`);
  execFileSync("ffmpeg", ["-v", "error", "-y", "-ss", at, "-i", MP4, "-frames:v", "1", "-vf", "scale=480:-1", file]);
}
const files = readdirSync(DIR).filter((f) => f.endsWith(".png")).sort();
const cols = 6;
const rows = Math.ceil(files.length / cols);
execFileSync("ffmpeg", [
  "-v", "error", "-y",
  "-framerate", "1", "-pattern_type", "glob", "-i", join(DIR, "*.png"),
  "-vf", `tile=${cols}x${rows}:padding=6:color=0x333333`,
  "-frames:v", "1", join(VIDEO, "out", "cuts.png"),
]);
console.log(`${files.length} cut(s) -> out/cuts/ and out/cuts.png`);
