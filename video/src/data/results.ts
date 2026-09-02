/**
 * The video's numbers, read off the frozen demo run and nothing else.
 *
 * Nothing in `src/scenes` or `src/components` may contain a literal figure.
 * The three files arrive as `unknown` (see `src/results.d.ts`) and every
 * field a scene cites is pulled through a named accessor here. A missing or
 * mistyped field throws with the file and the dotted path, at module
 * evaluation, so the bundle fails before a single frame is drawn. A JSON key
 * renamed upstream therefore breaks the build rather than the video.
 *
 * Field names mirror `src/sonar/models.py`: Receipt, StatsFile and Digest.
 */

export interface Incumbent {
  name: string;
  priceUsdMonth: number;
  url: string;
  checkedAt: string;
  mentionsQuota: number;
}

export interface Totals {
  monidUsd: number;
  monidRuns: number;
  monidRunsBilled: number;
  monidRunsZeroResults: number;
  monidRunsFailed: number;
  llmUsd: number;
  llmTokens: number;
  elevenlabsUsd: number;
  totalUsd: number;
}

export interface Comparison {
  briefsPerMonthAssumed: number;
  sonarUsdMonthEquiv: number;
  ratio: number | null;
  mentionsThisBrief: number;
}

export interface MentionCounts {
  fetched: number;
  deduped: number;
  labelled: number;
  bySource: Record<string, number>;
}

export interface RunRow {
  localSeq: number;
  runId: string | null;
  provider: string;
  endpoint: string;
  source: string | null;
  status: string;
  nResults: number | null;
  costUsd: number | null;
  costSource: string;
}

export interface Receipt {
  sessionId: string;
  verdict: string;
  replay: boolean;
  brand: string;
  competitors: string[];
  profile: string;
  incumbent: Incumbent;
  totals: Totals;
  comparison: Comparison;
  mentions: MentionCounts;
  runs: RunRow[];
  whatCouldNotBeChecked: string[];
}

export interface SovRow {
  brand: string;
  n: number;
  nClusters: number;
  share: number | null;
}

export interface SentimentRow {
  brand: string;
  n: number;
  pos: number;
  neg: number;
  neu: number;
  net: number | null;
}

export interface BySourceRow {
  brand: string;
  source: string;
  n: number;
  net: number | null;
}

export interface EventRow {
  brand: string;
  date: string;
  n: number;
  label: string;
}

export interface Stats {
  windowStart: string;
  windowEnd: string;
  shareOfVoice: SovRow[];
  sentiment: SentimentRow[];
  bySource: BySourceRow[];
  events: EventRow[];
}

export interface TopicRow {
  topicId: string;
  name: string;
  n: number;
  share: number | null;
  net: number | null;
}

export interface TopMentionRow {
  mentionId: string;
  source: string;
  url: string | null;
  quote: string;
  label: string;
}

export interface Digest {
  brand: string;
  topics: TopicRow[];
  topMentions: TopMentionRow[];
  coverageGaps: { source: string; reason: string }[];
  narrationChars: number;
  narrationNumbersVerified: boolean;
  costVerdict: string;
}

export interface Results {
  receipt: Receipt;
  stats: Stats;
  digest: Digest;
}

// ---------------------------------------------------------------------------
// Accessors. Each names the file and the dotted path in its error.
// ---------------------------------------------------------------------------

type Json = Record<string, unknown>;

const isObject = (v: unknown): v is Json => typeof v === "object" && v !== null && !Array.isArray(v);

class Reader {
  private readonly file: string;
  private readonly root: unknown;

  constructor(file: string, root: unknown) {
    this.file = file;
    this.root = root;
  }

  private at(path: string): unknown {
    let cur: unknown = this.root;
    for (const key of path.split(".")) {
      if (!isObject(cur) || !(key in cur)) {
        throw new Error(`results/demo/${this.file}: ${path} is missing`);
      }
      cur = cur[key];
    }
    return cur;
  }

  private fail(path: string, expected: string): never {
    throw new Error(`results/demo/${this.file}: ${path} is not ${expected}`);
  }

  num(path: string): number {
    const v = this.at(path);
    return typeof v === "number" && Number.isFinite(v) ? v : this.fail(path, "a number");
  }

  numOrNull(path: string): number | null {
    const v = this.at(path);
    if (v === null) return null;
    return typeof v === "number" && Number.isFinite(v) ? v : this.fail(path, "a number or null");
  }

  int(path: string): number {
    const v = this.num(path);
    return Number.isInteger(v) ? v : this.fail(path, "an integer");
  }

  intOrNull(path: string): number | null {
    const v = this.numOrNull(path);
    return v === null || Number.isInteger(v) ? v : this.fail(path, "an integer or null");
  }

  str(path: string): string {
    const v = this.at(path);
    return typeof v === "string" ? v : this.fail(path, "a string");
  }

  strOrNull(path: string): string | null {
    const v = this.at(path);
    if (v === null) return null;
    return typeof v === "string" ? v : this.fail(path, "a string or null");
  }

  bool(path: string): boolean {
    const v = this.at(path);
    return typeof v === "boolean" ? v : this.fail(path, "a boolean");
  }

  strings(path: string): string[] {
    const v = this.at(path);
    if (!Array.isArray(v) || !v.every((x) => typeof x === "string")) {
      this.fail(path, "a list of strings");
    }
    return v as string[];
  }

  /** Each element of a list, read through its own Reader rooted at `path[i]`. */
  list<Row>(path: string, row: (r: Reader) => Row): Row[] {
    const v = this.at(path);
    if (!Array.isArray(v)) this.fail(path, "a list");
    return (v as unknown[]).map((item, i) => row(new Reader(this.file, item).nested(`${path}[${i}]`)));
  }

  /** Integer-valued map, e.g. mentions.by_source. */
  intMap(path: string): Record<string, number> {
    const v = this.at(path);
    if (!isObject(v)) this.fail(path, "an object");
    const out: Record<string, number> = {};
    for (const [k, val] of Object.entries(v as Json)) {
      if (typeof val !== "number" || !Number.isInteger(val)) this.fail(`${path}.${k}`, "an integer");
      out[k] = val as number;
    }
    return out;
  }

  /** A reader whose error paths are prefixed, so a bad row names its index. */
  private nested(prefix: string): Reader {
    return new Reader(`${this.file} ${prefix}`, this.root);
  }
}

const readReceipt = (r: Reader): Receipt => ({
  sessionId: r.str("session_id"),
  verdict: r.str("verdict"),
  replay: r.bool("replay"),
  brand: r.str("query.brand"),
  competitors: r.strings("query.competitors"),
  profile: r.str("query.profile"),
  incumbent: {
    name: r.str("incumbent.name"),
    priceUsdMonth: r.int("incumbent.price_usd_month"),
    url: r.str("incumbent.url"),
    checkedAt: r.str("incumbent.checked_at"),
    mentionsQuota: r.int("incumbent.mentions_quota"),
  },
  totals: {
    monidUsd: r.num("totals.monid_usd"),
    monidRuns: r.int("totals.monid_runs"),
    monidRunsBilled: r.int("totals.monid_runs_billed"),
    monidRunsZeroResults: r.int("totals.monid_runs_zero_results"),
    monidRunsFailed: r.int("totals.monid_runs_failed"),
    llmUsd: r.num("totals.llm_usd"),
    llmTokens: r.int("totals.llm_tokens"),
    elevenlabsUsd: r.num("totals.elevenlabs_usd"),
    totalUsd: r.num("totals.total_usd"),
  },
  comparison: {
    briefsPerMonthAssumed: r.int("comparison.briefs_per_month_assumed"),
    sonarUsdMonthEquiv: r.num("comparison.sonar_usd_month_equiv"),
    ratio: r.numOrNull("comparison.ratio"),
    mentionsThisBrief: r.int("comparison.mentions_this_brief"),
  },
  mentions: {
    fetched: r.int("mentions.fetched"),
    deduped: r.int("mentions.deduped"),
    labelled: r.int("mentions.labelled"),
    bySource: r.intMap("mentions.by_source"),
  },
  runs: r.list("runs", (row) => ({
    localSeq: row.int("local_seq"),
    runId: row.strOrNull("run_id"),
    provider: row.str("provider"),
    endpoint: row.str("endpoint"),
    source: row.strOrNull("source"),
    status: row.str("status"),
    nResults: row.intOrNull("n_results"),
    costUsd: row.numOrNull("cost_usd"),
    costSource: row.str("cost_source"),
  })),
  whatCouldNotBeChecked: r.strings("what_could_not_be_checked"),
});

const readStats = (r: Reader): Stats => ({
  windowStart: r.str("window.current.start"),
  windowEnd: r.str("window.current.end"),
  shareOfVoice: r.list("share_of_voice", (row) => ({
    brand: row.str("brand"),
    n: row.int("n"),
    nClusters: row.int("n_clusters"),
    share: row.numOrNull("share"),
  })),
  sentiment: r.list("sentiment", (row) => ({
    brand: row.str("brand"),
    n: row.int("n"),
    pos: row.int("pos"),
    neg: row.int("neg"),
    neu: row.int("neu"),
    net: row.numOrNull("net"),
  })),
  bySource: r.list("by_source", (row) => ({
    brand: row.str("brand"),
    source: row.str("source"),
    n: row.int("n"),
    net: row.numOrNull("net"),
  })),
  events: r.list("events", (row) => ({
    brand: row.str("brand"),
    date: row.str("date"),
    n: row.int("n"),
    label: row.str("label"),
  })),
});

const readDigest = (r: Reader): Digest => ({
  brand: r.str("brand"),
  topics: r.list("topics", (row) => ({
    topicId: row.str("topic_id"),
    name: row.str("name"),
    n: row.int("n"),
    share: row.numOrNull("share"),
    net: row.numOrNull("net"),
  })),
  topMentions: r.list("top_mentions", (row) => ({
    mentionId: row.str("mention_id"),
    source: row.str("source"),
    url: row.strOrNull("url"),
    quote: row.str("quote"),
    label: row.str("label"),
  })),
  coverageGaps: r.list("coverage_gaps", (row) => ({
    source: row.str("source"),
    reason: row.str("reason"),
  })),
  narrationChars: r.int("narration.chars"),
  narrationNumbersVerified: r.bool("narration.numbers_verified"),
  costVerdict: r.str("cost.verdict"),
});

/**
 * Validates the three demo files. Called once, at import of `src/manifest.ts`.
 * Cross-file agreement is checked too: the digest's cost verdict is the
 * receipt's verdict, and the digest is about the receipt's brand.
 */
export const loadResults = (raw: { receipt: unknown; stats: unknown; digest: unknown }): Results => {
  const receipt = readReceipt(new Reader("receipt.json", raw.receipt));
  const stats = readStats(new Reader("stats.json", raw.stats));
  const digest = readDigest(new Reader("digest.json", raw.digest));
  if (digest.brand !== receipt.brand) {
    throw new Error(
      `results/demo: digest.json is about "${digest.brand}" but receipt.json is about "${receipt.brand}"`,
    );
  }
  if (digest.costVerdict !== receipt.verdict) {
    throw new Error(
      `results/demo: digest.json cost.verdict ${digest.costVerdict} disagrees with receipt.json verdict ${receipt.verdict}`,
    );
  }
  return { receipt, stats, digest };
};

/** Money on screen: two decimals, dollar sign, never rounded away from the file. */
export const usd = (v: number): string => `$${v.toFixed(2)}`;

/** Whole dollars, for the incumbent's list price. */
export const usdWhole = (v: number): string => `$${Math.round(v)}`;

export const fmt = (v: number): string => {
  if (Math.abs(v) < 1 && v !== 0) return v.toFixed(3).replace(/^(-?)0/, "$1");
  if (Number.isInteger(v)) return String(v);
  return v.toFixed(1);
};
