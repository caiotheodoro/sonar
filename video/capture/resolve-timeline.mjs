/**
 * The storyboard, resolved, as a table — and as an .srt when asked.
 *
 * Usage: node capture/resolve-timeline.mjs [--report] [--srt out/sonar.srt] [--json]
 */
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { resolveTimeline, timelineReport, timelineSrt } from "../src/timeline/resolve.mjs";

const VIDEO = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (p) => JSON.parse(readFileSync(join(VIDEO, "src", "data", p), "utf8"));

export const loadTimeline = () =>
  resolveTimeline({ storyboard: read("storyboard.json"), cues: read("narration.json").narration, grid: read("beat-grid.json"), fps: 30 });

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const t = loadTimeline();
  const srtAt = process.argv.indexOf("--srt");
  if (srtAt >= 0) {
    const out = resolve(VIDEO, process.argv[srtAt + 1]);
    mkdirSync(dirname(out), { recursive: true });
    writeFileSync(out, timelineSrt(t));
    console.log(`wrote ${out} (${t.cues.length} cues)`);
  } else if (process.argv.includes("--json")) {
    console.log(JSON.stringify({ totalMs: t.totalMs, totalFrames: t.totalFrames, shots: t.shots.map((s) => ({ id: s.shot.id, startMs: s.startMs, endMs: s.endMs, from: s.from, durationInFrames: s.durationInFrames })) }, null, 2));
  } else {
    console.log(timelineReport(t));
  }
}
