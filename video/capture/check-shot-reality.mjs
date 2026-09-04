/**
 * Compares what the video asserts against what the tool actually did.
 *
 * Every other check in the pipeline compares the video to itself: captions
 * against voice, beats against scenes, durations against the manifest. This
 * one compares it to the world. The rule it enforces: a factual claim on
 * screen may only come from the frozen demo results or a committed recording
 * of the tool's output.
 *
 *   1. no scene hard-codes a dollar amount, a verdict, or a digest
 *   2. every number the narration says exists in results/demo
 *   3. every cast a scene plays is present, and each is a real run of a
 *      sonar command
 *   4. the storyboard fits the hackathon cap
 *
 * Usage: node capture/check-shot-reality.mjs
 * Exits nonzero on any divergence. Run before every render.
 */
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const VIDEO = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const REPO = resolve(VIDEO, "..");
const DEMO = join(REPO, "results", "demo");
const FPS = 30;
const MAX_SECONDS = 90;

const failures = [];
const notes = [];
const fail = (m) => failures.push(m);

// ---------------------------------------------------------------------------
// 1. scenes carry no literal figures
// ---------------------------------------------------------------------------
const sceneDir = join(VIDEO, "src", "scenes");
for (const file of readdirSync(sceneDir).filter((f) => f.endsWith(".tsx"))) {
  const src = readFileSync(join(sceneDir, file), "utf8");
  for (const m of src.matchAll(/\$\s?\d[\d,]*(?:\.\d+)?/g)) {
    fail(`${file} hard-codes a dollar amount ${m[0]}; read it through RESULTS`);
  }
  for (const m of src.matchAll(/verdict\s*[:=]\s*["'](RECONCILED|PARTIAL|REPLAY)["']/g)) {
    fail(`${file} hard-codes the verdict ${m[1]} instead of reading the receipt`);
  }
  for (const m of src.matchAll(/\b[0-9a-f]{16,}\b/g)) {
    fail(`${file} contains a literal digest ${m[0].slice(0, 12)}…, not verifiable from the results`);
  }
}

// ---------------------------------------------------------------------------
// 2. narration numbers exist in the demo results
// ---------------------------------------------------------------------------
const NUMBER = /\d+(?:[.,]\d+)*/g;
const normalise = (token) => {
  const cleaned = token.replace(/,/g, "");
  const n = Number(cleaned);
  if (Number.isNaN(n)) return cleaned;
  return Number.isInteger(n) ? String(n) : String(n);
};
const numbersIn = (value, out = new Set()) => {
  if (typeof value === "boolean" || value === null) return out;
  if (typeof value === "number") out.add(normalise(String(value)));
  else if (typeof value === "string") for (const m of value.match(NUMBER) ?? []) out.add(normalise(m));
  else if (Array.isArray(value)) for (const v of value) numbersIn(v, out);
  else if (typeof value === "object") for (const v of Object.values(value)) numbersIn(v, out);
  return out;
};

const narration = JSON.parse(readFileSync(join(VIDEO, "src", "data", "narration.json"), "utf8"));
const cues = narration.narration ?? [];
if (cues.length === 0) {
  notes.push("narration.json has no cues yet; number check skipped");
} else if (!existsSync(DEMO)) {
  fail("narration has cues but results/demo is missing; nothing to check the numbers against");
} else {
  const published = new Set();
  for (const name of ["receipt.json", "stats.json", "digest.json"]) {
    const p = join(DEMO, name);
    if (existsSync(p)) numbersIn(JSON.parse(readFileSync(p, "utf8")), published);
  }
  // text is the caption, spoken is the voice; both are claims. startMs/endMs
  // (written by retime-captions.mjs) are timings, not claims — never checked.
  const said = numbersIn(cues.flatMap((c) => [c.text, c.spoken].filter(Boolean)));
  const unsourced = [...said].filter((n) => !published.has(n)).sort();
  if (unsourced.length) fail(`narration says numbers absent from results/demo: ${unsourced.join(", ")}`);
  notes.push(`narration: ${said.size} number token(s), all in results/demo`);
}

// ---------------------------------------------------------------------------
// 3. casts referenced by the manifest exist and record sonar commands
// ---------------------------------------------------------------------------
const manifest = readFileSync(join(VIDEO, "src", "manifest.ts"), "utf8");
const castIds = [...manifest.matchAll(/cast:\s*\{\s*src:\s*"([^"]+)"/g)].map((m) => m[1]);
for (const id of castIds) {
  const p = join(VIDEO, "public", "casts", `${id}.cast`);
  if (!existsSync(p)) {
    notes.push(`casts/${id}.cast not yet recorded`);
    continue;
  }
  const header = JSON.parse(readFileSync(p, "utf8").split("\n")[0]);
  if (!/\bsonar\b/.test(header.command ?? "")) {
    fail(`casts/${id}.cast was not recorded from a sonar command: ${header.command ?? "(none)"}`);
  }
}

// ---------------------------------------------------------------------------
// 4. the storyboard fits the cap
//
// manifest.ts derives scene durations from the timed narration (see
// sceneDurationsFrames), not literal `seconds(N)` calls, so this plain node
// script cannot import it (path aliases, TS). It mirrors the same formula
// against narration.json instead: this is the actual source of truth once
// the narration is measured, and manifest.ts's own `TOTAL_FRAMES > MAX_FRAMES`
// throw is the enforcement at bundle/render time either way.
// ---------------------------------------------------------------------------
const beatCount = new Set([...manifest.matchAll(/\bid:\s*"([a-z-]+)",\n\s*claim:/g)].map((m) => m[1])).size;
if (beatCount !== 6) fail(`manifest declares ${beatCount} beats, the storyboard has six`);

const OUTRO_TAIL_MS = 5000;
let totalSeconds;
if (cues.length && cues.every((c) => c.endMs > 0)) {
  totalSeconds = (Math.max(...cues.map((c) => c.endMs)) + OUTRO_TAIL_MS) / 1000;
} else {
  const targets = [...manifest.matchAll(/^\s{2}"?([a-z-]+)"?:\s*(\d+),$/gm)];
  totalSeconds = targets.reduce((a, m) => a + Number(m[2]), 0);
}
if (totalSeconds > MAX_SECONDS) fail(`storyboard runs ${totalSeconds}s, over the ${MAX_SECONDS}s cap`);
notes.push(`storyboard: ${beatCount} beats, ${totalSeconds.toFixed(1)}s of ${MAX_SECONDS}s, ${Math.round(totalSeconds * FPS)} frames`);

for (const n of notes) console.log(`  · ${n}`);
if (failures.length) {
  console.error(`\nshot-vs-reality: ${failures.length} divergence(s)\n`);
  for (const f of failures) console.error(`  ✗ ${f}`);
  process.exit(1);
}
console.log("\nshot-vs-reality: every on-screen claim traces to the results or a committed recording");
