/**
 * Emits the spoken narration for sonar's own TTS path.
 *
 * The voice is not generated here. Sonar already owns an ElevenLabs call
 * through Monid, and that call has to appear on the ledger and the receipt
 * like every other run, so the narration is produced by sonar and not by a
 * side channel with its own API key. This script does the one thing the
 * video pipeline is responsible for: it turns narration.json into the exact
 * text to speak, with beat pauses as paragraph breaks, and writes it to
 * public/narration.txt for that run to read.
 *
 * `spoken` overrides `text` for the voice only. A cue that starts a new scene
 * is preceded by a blank line, so the pause between beats is a real paragraph
 * break rather than something inferred from punctuation.
 *
 * Usage: node capture/generate-voice.mjs
 */
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spokenOf } from "./emit-voicescript.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const VIDEO = resolve(HERE, "..");
const OUT = join(VIDEO, "public", "narration.txt");

const file = JSON.parse(readFileSync(join(VIDEO, "src", "data", "narration.json"), "utf8"));
const cues = file.narration;
if (!Array.isArray(cues) || cues.length === 0) {
  console.error("narration.json has no cues; nothing to speak");
  process.exit(1);
}
const text = spokenOf(cues);
mkdirSync(dirname(OUT), { recursive: true });
writeFileSync(OUT, `${text}\n`);
console.log(
  `${text.split(/\s+/).length} words, ${text.length} chars -> public/narration.txt. ` +
    "Speak it through sonar's voice path so the run lands on the receipt, then save the mp3 as public/narration.mp3.",
);
