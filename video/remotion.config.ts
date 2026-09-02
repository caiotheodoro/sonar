import path from "node:path";
import { Config } from "@remotion/cli/config";

Config.setRspack(true);
Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
Config.setChromiumOpenGlRenderer("angle");

/**
 * `@results` and `@results-empty` resolve to the frozen demo runs one level
 * above this package. They are aliases rather than relative imports so the
 * type-checker can fall back to the ambient declaration in src/results.d.ts
 * while the runs do not exist yet; the bundler has no such fallback, so a
 * render with a missing file fails here, at build time, by design.
 */
const RESULTS = path.join(process.cwd(), "..", "results");

Config.overrideBundlerConfig((config) => ({
  ...config,
  resolve: {
    ...config.resolve,
    alias: {
      ...(config.resolve?.alias ?? {}),
      "@": path.join(process.cwd(), "src"),
      "@results": path.join(RESULTS, "demo"),
      "@results-empty": path.join(RESULTS, "demo-empty"),
    },
  },
}));
