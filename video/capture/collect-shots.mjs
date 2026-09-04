/**
 * Reads every public/shots/<name>.png (IHDR) and its sidecar into
 * src/data/shots.json, so a scene knows a screenshot's size without waiting
 * on the image. Fails if a sidecar's dims disagree with the PNG.
 *
 * Usage: node capture/collect-shots.mjs
 */
import { existsSync, readFileSync, readdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const VIDEO = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const DIR = join(VIDEO, "public", "shots");
const OUT = join(VIDEO, "src", "data", "shots.json");

export const pngSize = (file) => {
  const b = readFileSync(file);
  if (b.toString("ascii", 1, 4) !== "PNG") throw new Error(`${file}: not a PNG`);
  return { width: b.readUInt32BE(16), height: b.readUInt32BE(20) };
};

export const collect = () => {
  const out = {};
  if (!existsSync(DIR)) return out;
  for (const f of readdirSync(DIR).filter((f) => f.endsWith(".png")).sort()) {
    const name = f.slice(0, -4);
    const { width, height } = pngSize(join(DIR, f));
    const sidecarPath = join(DIR, `${name}.json`);
    if (!existsSync(sidecarPath)) throw new Error(`public/shots/${name}.json sidecar missing`);
    const sc = JSON.parse(readFileSync(sidecarPath, "utf8"));
    if (sc.width !== width || sc.height !== height) {
      throw new Error(`public/shots/${name}: sidecar says ${sc.width}×${sc.height}, PNG is ${width}×${height}`);
    }
    out[name] = { width, height, url: sc.url, captured_at: sc.captured_at };
  }
  return out;
};

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const shots = collect();
  writeFileSync(OUT, `${JSON.stringify(shots, null, 2)}\n`);
  console.log(`${Object.keys(shots).length} shot(s) -> src/data/shots.json`);
  for (const [k, v] of Object.entries(shots)) console.log(`  ${k.padEnd(24)} ${v.width}×${v.height}  ${v.url}`);
}
