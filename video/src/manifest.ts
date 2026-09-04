/**
 * Constants and the frozen results. The cut itself lives in
 * src/data/storyboard.json and is resolved by src/timeline.
 *
 * Every number on screen comes from the frozen demo runs through `RESULTS`
 * and `RESULTS_EMPTY`, or from src/data/external-facts.json through
 * `fact()`. The results files are imported by alias so a tree without them
 * still type-checks, while bundling and rendering fail (see
 * `remotion.config.ts` and `src/results.d.ts`).
 */
import receiptRaw from "@results/receipt.json";
import statsRaw from "@results/stats.json";
import digestRaw from "@results/digest.json";
import receiptEmptyRaw from "@results-empty/receipt.json";
import statsEmptyRaw from "@results-empty/stats.json";
import digestEmptyRaw from "@results-empty/digest.json";
import { loadResultsFrom } from "./data/results";

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;

/** The demo run, validated field by field. Throws at import when a cited number is absent. */
export const RESULTS = loadResultsFrom("demo", {
  receipt: receiptRaw,
  stats: statsRaw,
  digest: digestRaw,
});

/** The zero-mention run (Zephyrium Bank): a receipt reconciles with nothing to find. */
export const RESULTS_EMPTY = loadResultsFrom("demo-empty", {
  receipt: receiptEmptyRaw,
  stats: statsEmptyRaw,
  digest: digestEmptyRaw,
});

export const PUBLISHED = {
  code: "github.com/caiotheodoro/sonar",
  hashtag: "#monid",
} as const;
