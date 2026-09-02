/**
 * Ambient fallback for the results aliases.
 *
 * `@results/receipt.json` resolves through tsconfig `paths` to
 * ../results/demo/receipt.json when that file exists and gets its real JSON
 * type. Until the demo run is frozen the path does not resolve, and TypeScript
 * falls back to this wildcard declaration, so `pnpm lint` stays green on a
 * scaffold. The value is deliberately `unknown`: every field the video shows
 * passes through the typed loader in src/data/loader.ts, which throws at
 * bundle time naming the exact path that is missing. The bundler itself has no
 * fallback, so a render without the files fails before a frame is drawn.
 */
declare module "@results/*" {
  const value: unknown;
  export default value;
}

declare module "@results-empty/*" {
  const value: unknown;
  export default value;
}
