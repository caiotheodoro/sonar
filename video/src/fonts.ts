/**
 * Two families, one role each: Geist Mono for everything structural (the big
 * figures, the tables, the terminal — the price and the cost share the
 * terminal's face, which is the thesis), Space Grotesk for captions and labels.
 * Only the weights and subsets the video uses — loading full families made
 * Remotion warn about ~250 network requests per render.
 */
import { loadFont as loadMono } from "@remotion/google-fonts/GeistMono";
import { loadFont as loadCaption } from "@remotion/google-fonts/SpaceGrotesk";

export const { fontFamily: monoFamily } = loadMono("normal", {
  weights: ["400", "500", "700"],
  subsets: ["latin"],
});

export const { fontFamily: captionFamily } = loadCaption("normal", {
  weights: ["500", "600"],
  subsets: ["latin"],
});

/** Back-compat alias: `sansFamily` is the caption face. */
export const sansFamily = captionFamily;
