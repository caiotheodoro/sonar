/**
 * Compares what the video asserts against what the tool actually did.
 *
 * The rule: a factual claim on screen may only come from the frozen results,
 * a committed recording of the tool's output, or a quoted third-party fact
 * backed by a committed, reviewed screenshot of the page it was read from.
 *
 *   1. no card, shot or component hard-codes a dollar amount, a verdict, a
 *      digest, or the words "all billed"
 *   2. every number the narration or a stamp says exists in results/demo,
 *      results/demo-empty, or external-facts.json (whose shot is tracked)
 *   3. every cast the storyboard plays is a real run of a sonar command
 *   4. the storyboard resolves: contiguous, in act order, under the cap
 *   5. every screenshot exists, is tracked with its sidecar, is reviewed
 *   6. the generated data files are fresh against the assets they describe
 *   7. no wording implies "billed" and "empty" partition the runs
 *
 * Usage: node capture/check-shot-reality.mjs
 * Exits nonzero on any divergence. Run before every render.
 */
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { resolveTimeline } from "../src/timeline/resolve.mjs";
import { collect } from "./collect-shots.mjs";

const VIDEO = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const REPO = resolve(VIDEO, "..");
const DATA = join(VIDEO, "src", "data");
const MAX_MS = 90000;
const TARGET_NOTE_MS = 66000;

const failures = [];
const notes = [];
const fail = (m) => failures.push(m);
const readJson = (p) => JSON.parse(readFileSync(p, "utf8"));
const tracked = new Set(execFileSync("git", ["ls-files"], { cwd: REPO, encoding: "utf8" }).split("\n").filter(Boolean));
const isTracked = (rel) => tracked.has(rel.replace(/\\/g, "/"));
const sha = (p) => createHash("sha256").update(readFileSync(p)).digest("hex");

// ---------------------------------------------------------------------------
// 1. no literal figures in the drawing code
// ---------------------------------------------------------------------------
const walk = (dir) => readdirSync(dir, { withFileTypes: true }).flatMap((d) => (d.isDirectory() ? walk(join(dir, d.name)) : d.name.endsWith(".tsx") ? [join(dir, d.name)] : []));
for (const file of ["cards", "shots", "components", "scenes"].flatMap((d) => (existsSync(join(VIDEO, "src", d)) ? walk(join(VIDEO, "src", d)) : []))) {
  const src = readFileSync(file, "utf8");
  const rel = file.slice(VIDEO.length + 1);
  for (const m of src.matchAll(/\$\s?\d[\d,]*(?:\.\d+)?/g)) fail(`${rel} hard-codes a dollar amount ${m[0]}; read it through RESULTS or fact()`);
  for (const m of src.matchAll(/verdict\s*[:=]\s*["'](RECONCILED|PARTIAL|REPLAY)["']/g)) fail(`${rel} hard-codes the verdict ${m[1]}`);
  for (const m of src.matchAll(/\b[0-9a-f]{16,}\b/g)) fail(`${rel} contains a literal digest ${m[0].slice(0, 12)}…`);
  if (/all billed/i.test(src)) fail(`${rel} says "all billed"; billed and zero-result overlap, and not every run is billed`);
}

// ---------------------------------------------------------------------------
// 2. number provenance
// ---------------------------------------------------------------------------
const NUMBER = /\d+(?:[.,]\d+)*/g;
const normalise = (token) => {
  const cleaned = token.replace(/,/g, "");
  const n = Number(cleaned);
  return Number.isNaN(n) ? cleaned : String(n);
};
const numbersIn = (value, out = new Set()) => {
  if (typeof value === "boolean" || value === null || value === undefined) return out;
  if (typeof value === "number") out.add(normalise(String(value)));
  else if (typeof value === "string") for (const m of value.match(NUMBER) ?? []) out.add(normalise(m));
  else if (Array.isArray(value)) for (const v of value) numbersIn(v, out);
  else if (typeof value === "object") for (const v of Object.values(value)) numbersIn(v, out);
  return out;
};

const narrationFile = readJson(join(DATA, "narration.json"));
const cues = narrationFile.narration ?? [];
const storyboard = readJson(join(DATA, "storyboard.json"));
const facts = readJson(join(DATA, "external-facts.json")).facts;
const grid = readJson(join(DATA, "beat-grid.json"));

const published = new Set();
for (const dir of ["demo", "demo-empty"]) {
  for (const name of ["receipt.json", "stats.json", "digest.json"]) {
    const p = join(REPO, "results", dir, name);
    if (existsSync(p)) numbersIn(readJson(p), published);
    else fail(`results/${dir}/${name} is missing; nothing to check the numbers against`);
  }
}
const shotTracked = (name) => isTracked(`video/public/shots/${name}.png`) && isTracked(`video/public/shots/${name}.json`);
for (const f of facts) {
  if (!shotTracked(f.shot)) {
    fail(`external fact "${f.id}" cites shot "${f.shot}" which is not tracked (png + json sidecar); the number is unusable until it is`);
    continue;
  }
  numbersIn(f.value, published);
  numbersIn(f.display, published);
}
const receipt = readJson(join(REPO, "results", "demo", "receipt.json"));
const team = facts.find((f) => f.id === "brand24.price.team");
if (!team) fail(`external-facts.json has no "brand24.price.team"`);
else if (team.value !== receipt.incumbent.price_usd_month) fail(`external fact brand24.price.team (${team.value}) ≠ receipt incumbent.price_usd_month (${receipt.incumbent.price_usd_month})`);

const said = numbersIn(cues.flatMap((c) => [c.text, c.spoken].filter(Boolean)));
numbersIn(storyboard.shots.flatMap((s) => [s.text, ...(s.plate ?? [])].filter(Boolean)), said);
const unsourced = [...said].filter((n) => !published.has(n)).sort();
if (unsourced.length) fail(`narration/stamps say numbers absent from results/ and external facts: ${unsourced.join(", ")}`);
notes.push(`claims: ${said.size} number token(s) in narration + stamps, all sourced`);

// ---------------------------------------------------------------------------
// 3. casts
// ---------------------------------------------------------------------------
for (const s of storyboard.shots.filter((s) => s.kind === "cast")) {
  const p = join(VIDEO, "public", "casts", `${s.src}.cast`);
  if (!existsSync(p)) {
    fail(`shot "${s.id}": casts/${s.src}.cast is not recorded`);
    continue;
  }
  const header = JSON.parse(readFileSync(p, "utf8").split("\n")[0]);
  if (!/\bsonar\b/.test(header.command ?? "")) fail(`casts/${s.src}.cast was not recorded from a sonar command: ${header.command ?? "(none)"}`);
  if (!existsSync(join(DATA, "casts", `${s.src}.json`))) fail(`src/data/casts/${s.src}.json missing; run capture/emit-cast-json.mjs`);
}

// ---------------------------------------------------------------------------
// 4. the storyboard resolves
// ---------------------------------------------------------------------------
let timeline = null;
try {
  timeline = resolveTimeline({ storyboard, cues, grid, fps: 30 });
  if (timeline.totalMs > MAX_MS) fail(`the cut runs ${timeline.totalMs} ms, over the ${MAX_MS} ms cap`);
  if (timeline.totalMs > TARGET_NOTE_MS) notes.push(`cut is ${timeline.totalMs} ms; the target is 60 s`);
  const cardsSrc = readFileSync(join(VIDEO, "src", "cards", "index.ts"), "utf8");
  const cardIds = new Set([...cardsSrc.matchAll(/^\s+"?([a-z-]+)"?:\s*[A-Z]/gm)].map((m) => m[1]));
  const rowIds = new Set(["runs", "billed", "zero", "failed", "verdict", "monid", "llm", "voice", "total", "monthly", "mentions"]);
  for (const s of storyboard.shots) {
    if (s.kind === "card" && !cardIds.has(s.card)) fail(`shot "${s.id}": no card "${s.card}" in src/cards/index.ts`);
    if (s.kind === "receipt") for (const r of s.rows) if (!rowIds.has(r)) fail(`shot "${s.id}": unknown receipt row "${r}"`);
  }
  const longShots = timeline.shots.filter((r) => r.shot.kind === "shot" && r.endMs - r.startMs > 2500);
  if (longShots.length) notes.push(`${longShots.length} screenshot(s) held over 2.5 s: ${longShots.map((r) => r.shot.id).join(", ")}`);
  notes.push(`storyboard: ${timeline.shots.length} shots, ${storyboard.acts.length} acts, ${timeline.totalMs} ms, ${timeline.totalFrames} frames, narration ${timeline.narrationMeasured ? "measured" : "UNMEASURED"}`);
  if (!timeline.narrationMeasured) fail("narration.json is unmeasured; run capture/measure-cues.mjs after saving public/narration.mp3");
} catch (e) {
  fail(`storyboard does not resolve: ${e.message}`);
}

// ---------------------------------------------------------------------------
// 5. screenshots
// ---------------------------------------------------------------------------
const shotNames = new Set([...storyboard.shots.filter((s) => s.kind === "shot").map((s) => s.src), ...facts.map((f) => f.shot)]);
let shots = {};
try {
  shots = collect();
} catch (e) {
  fail(`public/shots: ${e.message}`);
}
for (const name of shotNames) {
  const png = join(VIDEO, "public", "shots", `${name}.png`);
  const sc = join(VIDEO, "public", "shots", `${name}.json`);
  if (!existsSync(png)) {
    fail(`public/shots/${name}.png is missing; run capture/shoot.mjs --only ${name}`);
    continue;
  }
  if (!existsSync(sc)) {
    fail(`public/shots/${name}.json sidecar is missing`);
    continue;
  }
  if (!shotTracked(name)) fail(`public/shots/${name}.png/.json are not tracked by git`);
  const meta = readJson(sc);
  if (meta.pii_reviewed !== true) fail(`public/shots/${name}.json: pii_reviewed is not true; look at the PNG, then set it`);
  if (!/^https:\/\//.test(meta.url ?? "")) fail(`public/shots/${name}.json: url must be https`);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(meta.captured_at ?? "")) fail(`public/shots/${name}.json: captured_at must be a date`);
  const host = new URL(meta.url).host;
  if (host === "app.monid.ai" && !(meta.redactions ?? []).length) fail(`public/shots/${name}.json: a logged-in app capture needs at least one redaction`);
  for (const f of facts.filter((f) => f.shot === name)) {
    if (new URL(f.source_url).host !== host) fail(`external fact "${f.id}" cites ${f.source_url} but its shot was captured from ${meta.url}`);
  }
  for (const s of storyboard.shots.filter((s) => s.kind === "shot" && s.src === name)) {
    const c = s.crop;
    if (c && (c.x < 0 || c.y < 0 || c.x + c.w > meta.width || c.y + c.h > meta.height)) fail(`shot "${s.id}": crop ${JSON.stringify(c)} exceeds ${meta.width}×${meta.height}`);
    const h = s.highlight;
    if (h && (h.x < 0 || h.y < 0 || h.x + h.w > meta.width || h.y + h.h > meta.height)) fail(`shot "${s.id}": highlight exceeds the capture`);
  }
}
const unusedFacts = facts.filter((f) => !storyboard.shots.some((s) => s.kind === "shot" && (s.facts ?? []).includes(f.id)) && !said.has(normalise(String(f.value))));
if (unusedFacts.length) notes.push(`external facts not shown or said: ${unusedFacts.map((f) => f.id).join(", ")}`);

// ---------------------------------------------------------------------------
// 6. freshness
// ---------------------------------------------------------------------------
const music = join(VIDEO, "public", storyboard.music.src);
if (!existsSync(music)) fail(`public/${storyboard.music.src} is missing`);
else if (sha(music) !== grid.trackSha256) fail(`beat-grid.json was built from a different ${storyboard.music.src}; re-run capture/beat-grid.py`);
const mp3 = join(VIDEO, "public", storyboard.narration.src);
if (!existsSync(mp3)) fail(`public/${storyboard.narration.src} is missing`);
else if (narrationFile.measured?.mp3Sha256 && sha(mp3) !== narrationFile.measured.mp3Sha256) fail(`narration.json was measured against a different ${storyboard.narration.src}; re-run capture/measure-cues.mjs`);
const repoFacts = readJson(join(DATA, "repo-facts.json"));
const headRev = execFileSync("git", ["rev-parse", "--short", "HEAD"], { cwd: REPO, encoding: "utf8" }).trim();
if (repoFacts.sonarRev !== headRev) notes.push(`repo-facts.json was collected at ${repoFacts.sonarRev}, HEAD is ${headRev}; run capture/collect-repo-facts.mjs before the final render`);
const shotsJson = readJson(join(DATA, "shots.json"));
if (JSON.stringify(shotsJson) !== JSON.stringify(shots)) fail("src/data/shots.json is stale; run capture/collect-shots.mjs");

// ---------------------------------------------------------------------------
// 7. wording
// ---------------------------------------------------------------------------
const spoken = cues.flatMap((c) => [c.text, c.spoken].filter(Boolean)).join(" ");
if (/(\d+|[a-z-]+) billed,? (\d+|[a-z-]+) (empty|zero)/i.test(spoken)) fail(`narration pairs "billed" with "empty" as if they partition the runs; a zero-result run is still billed`);
if (/all billed/i.test(spoken) && receipt.totals.monid_runs !== receipt.totals.monid_runs_billed) fail(`narration says "all billed" but ${receipt.totals.monid_runs_billed} of ${receipt.totals.monid_runs} runs were billed`);
for (const bad of [/brand24'?s numbers/i, /everything brand24 monitors/i, /same numbers/i, /\b(worse|bad|broken|overpriced|rip-?off)\b/i]) {
  if (bad.test(spoken)) fail(`narration matches ${bad}: nothing negative about the incumbent, no equivalence claim`);
}

for (const n of notes) console.log(`  · ${n}`);
if (failures.length) {
  console.error(`\nshot-vs-reality: ${failures.length} divergence(s)\n`);
  for (const f of failures) console.error(`  ✗ ${f}`);
  process.exit(1);
}
console.log("\nshot-vs-reality: every on-screen claim traces to the results, a committed recording, or a reviewed screenshot");
