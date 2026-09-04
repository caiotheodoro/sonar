/**
 * Two families, one role each: Big Shoulders (the merged variable family; the Display cut is not shipped as ESM) carries every stamp and
 * act title (condensed, industrial — the nameplate face); Geist Mono carries
 * every plate, spec value, figure and the one terminal shot. Only the weights
 * the cut uses — loading full families made Remotion warn about ~250 network
 * requests per render.
 */
import { loadFont as loadMono } from "@remotion/google-fonts/GeistMono";
import { loadFont as loadDisplay } from "@remotion/google-fonts/BigShoulders";

export const { fontFamily: monoFamily } = loadMono("normal", {
  weights: ["400", "500", "700"],
  subsets: ["latin"],
});

export const { fontFamily: displayFamily } = loadDisplay("normal", {
  weights: ["800", "900"],
  subsets: ["latin"],
});

/** Alias kept for the retained components. */
export const sansFamily = monoFamily;
export const captionFamily = monoFamily;
