/**
 * Pre-parses every recorded cast into src/data/casts/<id>.json.
 *
 * TerminalCast used to `fetch(staticFile(...))` a cast at runtime, behind
 * `delayRender`/`continueRender`. During a `<Sequence premountFor>` window —
 * exactly the frames the camera's shove between beats covers — Remotion does
 * not appear to block those frames' pixels on that delay, so the incoming
 * beat rendered blank for the length of the shove, then popped in fully
 * loaded the instant the beat became officially active. Parsing ahead of
 * time and importing the result as ordinary JSON removes the async gap
 * entirely: there is nothing left to load at render time.
 *
 * public/casts/<id>.cast stays the evidence file (what check-shot-reality.mjs
 * verifies came from a real `sonar` command); this script's output is a
 * derived, regenerable cache, the same relationship repo-facts.json has to
 * the repo it reads.
 *
 * Usage: node capture/emit-cast-json.mjs
 */
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const VIDEO = resolve(HERE, "..");
const CASTS_DIR = join(VIDEO, "public", "casts");
const OUT_DIR = join(VIDEO, "src", "data", "casts");

/** Mirrors TerminalCast.tsx's parseCast, so the JSON matches what it expects. */
const parseCast = (text) => {
  const lines = text.split("\n").filter((l) => l.trim().length > 0);
  const header = JSON.parse(lines[0]);
  const events = [];
  let clock = 0;
  for (const line of lines.slice(1)) {
    const row = JSON.parse(line);
    clock = header.version >= 3 ? clock + row[0] : row[0];
    events.push({ t: clock, kind: row[1], data: row[2] });
  }
  return { header, events, duration: events.length ? events[events.length - 1].t : 0 };
};

if (!existsSync(CASTS_DIR)) {
  console.log("public/casts/ does not exist yet; nothing to parse");
  process.exit(0);
}

mkdirSync(OUT_DIR, { recursive: true });
const files = readdirSync(CASTS_DIR).filter((f) => f.endsWith(".cast"));
for (const file of files) {
  const id = file.slice(0, -".cast".length);
  const cast = parseCast(readFileSync(join(CASTS_DIR, file), "utf8"));
  writeFileSync(join(OUT_DIR, `${id}.json`), `${JSON.stringify(cast)}\n`);
  console.log(`${id}: ${cast.events.length} events, ${cast.duration.toFixed(1)}s -> src/data/casts/${id}.json`);
}
