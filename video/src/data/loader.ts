/**
 * The typed loader every on-screen number passes through.
 *
 * A scene never reads a raw JSON object. It reads a field that `bind()` has
 * checked is present and of the declared kind, and if the field is missing the
 * whole bundle fails with the file and the dotted path in the message. That is
 * the structural guarantee behind "no number is typed": a number that is not
 * in the results cannot reach the screen, and a results file that lost a field
 * cannot render a stale frame.
 */

export type Kind = "number" | "string" | "boolean" | "array" | "object" | "number|null";

export interface Spec {
  /** Dotted path into the JSON, e.g. "totals.total_usd" or "runs[0].run_id". */
  path: string;
  kind: Kind;
}

const walk = (root: unknown, path: string): { found: boolean; value: unknown } => {
  const parts = path
    .replace(/\[(\d+)\]/g, ".$1")
    .split(".")
    .filter(Boolean);
  let cur: unknown = root;
  for (const part of parts) {
    if (cur === null || cur === undefined) return { found: false, value: undefined };
    if (Array.isArray(cur)) {
      const i = Number(part);
      if (!Number.isInteger(i) || i < 0 || i >= cur.length) return { found: false, value: undefined };
      cur = cur[i];
      continue;
    }
    if (typeof cur !== "object" || !(part in (cur as Record<string, unknown>))) {
      return { found: false, value: undefined };
    }
    cur = (cur as Record<string, unknown>)[part];
  }
  return { found: true, value: cur };
};

const isKind = (value: unknown, kind: Kind): boolean => {
  switch (kind) {
    case "number":
      return typeof value === "number" && Number.isFinite(value);
    case "number|null":
      return value === null || (typeof value === "number" && Number.isFinite(value));
    case "string":
      return typeof value === "string";
    case "boolean":
      return typeof value === "boolean";
    case "array":
      return Array.isArray(value);
    case "object":
      return typeof value === "object" && value !== null && !Array.isArray(value);
  }
};

/**
 * Check `raw` against `specs` and return it as `T`.
 *
 * `file` is only used in the error message; it is the path a reader should
 * open. Every missing or mistyped spec is reported at once rather than the
 * first, so one failed bundle lists everything the results file owes.
 */
export const bind = <T>(file: string, raw: unknown, specs: readonly Spec[]): T => {
  if (raw === undefined || raw === null || typeof raw !== "object") {
    throw new Error(`${file}: not a JSON object (got ${raw === null ? "null" : typeof raw})`);
  }
  const problems: string[] = [];
  for (const spec of specs) {
    const { found, value } = walk(raw, spec.path);
    if (!found) {
      problems.push(`${spec.path} is missing`);
    } else if (!isKind(value, spec.kind)) {
      problems.push(`${spec.path} is ${describe(value)}, expected ${spec.kind}`);
    }
  }
  if (problems.length) {
    throw new Error(
      `${file}: ${problems.length} cited field(s) unavailable, the video cannot show them:\n  ` +
        problems.join("\n  "),
    );
  }
  return raw as T;
};

const describe = (value: unknown): string => {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  return typeof value;
};

/** Format a dollar figure for the screen. Digits come from the caller; never literals. */
export const usd = (value: number, digits = 2): string =>
  `$${value.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;

/** Format a ratio such as 349 / 0.42 as "832x". */
export const times = (ratio: number | null): string =>
  ratio === null ? "n/a" : `${Math.round(ratio).toLocaleString("en-US")}x`;

/** Format a unit-interval share as a percentage with one decimal. */
export const pct = (share: number | null): string =>
  share === null ? "abstained" : `${(share * 100).toFixed(1)}%`;
