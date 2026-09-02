/**
 * Records the video's terminal shots as real asciinema casts.
 *
 * Every cast is a genuine run. Nothing here is typed out or reconstructed:
 * a tool whose argument is that a claim is not a result until it is on a
 * receipt does not get to fake its own terminal.
 *
 * The brand, competitors and profile come from the frozen demo receipt, so
 * the recording is of the same query the numbers on screen describe. Runs
 * that spend Monid or OpenAI credit are marked `spends` and refuse to start
 * unless SONAR_CAPTURE_SPEND=1 is set; their sessions are written under
 * public/captures so nothing touches results/demo.
 *
 * Usage:  node capture/record-casts.mjs [id ...]
 *         node capture/record-casts.mjs            # all of them
 */
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const VIDEO = resolve(HERE, "..");
const REPO = resolve(VIDEO, "..");
const OUT = join(VIDEO, "public", "casts");
const CAPTURES = join(VIDEO, "public", "captures");
const DEMO = join(REPO, "results", "demo");

/** 120x28 keeps output unwrapped and legible when scaled to 1080p. */
const WINDOW = process.env.CAST_WINDOW ?? "120x28";

const receiptPath = join(DEMO, "receipt.json");
if (!existsSync(receiptPath)) {
  console.error(`no frozen demo receipt at ${receiptPath}; the casts record that query`);
  process.exit(1);
}
const receipt = JSON.parse(readFileSync(receiptPath, "utf8"));
const brand = receipt.query.brand;
const competitors = receipt.query.competitors ?? [];
const vs = competitors.flatMap((c) => ["--vs", c]);
const quote = (s) => `'${String(s).replace(/'/g, `'\\''`)}'`;

const CASTS = [
  {
    id: "doctor",
    title: "keys, reachability, wallet",
    cmd: "uv run sonar doctor",
    spends: false,
  },
  {
    id: "run_trace",
    title: "a live POST /v1/run, traced",
    cmd: [
      "uv run sonar run --trace --profile lite --no-voice",
      quote(brand),
      ...vs.map(quote),
      "--out",
      quote(join(CAPTURES, "run_trace")),
    ].join(" "),
    spends: true,
  },
  {
    id: "receipt",
    title: "the receipt, verified",
    cmd: `uv run sonar verify ${quote(receiptPath)} && uv run sonar render --from ${quote(DEMO)}`,
    spends: false,
  },
  {
    id: "ask",
    title: "sonar ask, with citations",
    cmd: `uv run sonar ask ${quote(brand)} ${quote(process.env.SONAR_ASK_QUESTION ?? "What do people complain about most?")} --session ${quote(DEMO)}`,
    spends: true,
  },
  {
    id: "avenza_empty",
    title: "a brand with no mentions",
    cmd: `uv run sonar run --trace --profile lite --no-voice Avenza --out ${quote(join(CAPTURES, "avenza_empty"))}`,
    spends: true,
  },
];

const wanted = process.argv.slice(2);
const todo = wanted.length ? CASTS.filter((c) => wanted.includes(c.id)) : CASTS;

if (!todo.length) {
  console.error(`no cast matched. known ids: ${CASTS.map((c) => c.id).join(", ")}`);
  process.exit(1);
}
const spending = todo.filter((c) => c.spends);
if (spending.length && process.env.SONAR_CAPTURE_SPEND !== "1") {
  console.error(
    `${spending.map((c) => c.id).join(", ")} spend credit. Set SONAR_CAPTURE_SPEND=1 to record them.`,
  );
  process.exit(1);
}

mkdirSync(OUT, { recursive: true });
mkdirSync(CAPTURES, { recursive: true });

for (const cast of todo) {
  const out = join(OUT, `${cast.id}.cast`);
  process.stdout.write(`recording ${cast.id} ... `);
  const started = Date.now();
  execFileSync(
    "asciinema",
    [
      "rec",
      "--overwrite",
      "--headless",
      "--window-size", WINDOW,
      "--output-format", "asciicast-v2",
      "--title", cast.title,
      "--command", cast.cmd,
      out,
    ],
    { cwd: REPO, stdio: ["ignore", "ignore", "inherit"] },
  );
  console.log(`${((Date.now() - started) / 1000).toFixed(1)}s -> public/casts/${cast.id}.cast`);
}
