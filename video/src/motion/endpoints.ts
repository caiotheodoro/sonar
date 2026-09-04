/**
 * The receipt's runs, folded to one row per source and endpoint. The fan
 * lands on these rows, then the same rows grow prices: two shots, one list,
 * so the cut between them reads as the list continuing rather than a change
 * of subject.
 */
import { RESULTS } from "../manifest";

export interface EndpointRow {
  source: string;
  provider: string;
  endpoint: string;
  calls: number;
  usd: number;
  results: number;
}

const byKey = new Map<string, EndpointRow>();
for (const r of RESULTS.receipt.runs) {
  const source = r.source ?? "voice";
  const key = `${source}${r.endpoint}`;
  const row = byKey.get(key) ?? { source, provider: r.provider, endpoint: r.endpoint, calls: 0, usd: 0, results: 0 };
  row.calls += 1;
  row.usd += r.costUsd ?? 0;
  row.results += r.nResults ?? 0;
  byKey.set(key, row);
}

/** Dearest first: the fan lands in the order the ledger will read. */
export const ENDPOINT_ROWS: EndpointRow[] = [...byKey.values()].sort((a, b) => b.usd - a.usd);
