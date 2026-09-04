/**
 * The sound library, as names. Every file is synthesised by
 * capture/sfx.py into public/sfx/<name>.wav; the gate checks each exists.
 */
import storyboard from "./data/storyboard.json";

export const SFX_NAMES = ["tick", "key", "shutter", "click", "blip", "sweep", "whoosh", "hit", "stamp", "chime"] as const;
export type SfxName = (typeof SFX_NAMES)[number];

/** Bus gain for every effect, from storyboard.json `sfx.volume`. */
export const SFX_BUS: number = (storyboard as { sfx?: { volume?: number } }).sfx?.volume ?? 0.7;
