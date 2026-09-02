/**
 * Beat 2: the live POST /v1/run trace. The final scene replays
 * public/casts/run_trace.cast byte for byte; until it is recorded the beat
 * shows the run list the receipt says happened, so the two can be compared.
 */
import React from "react";
import { BeatPlaceholder } from "../components/BeatPlaceholder";
import { Column, Row, Source, Table } from "../components/DataPanel";
import { usd } from "../data/results";
import { RESULTS } from "../manifest";

const { runs, totals } = RESULTS.receipt;

const columns: Column[] = [
  { key: "seq", label: "#", numeric: true, width: 80 },
  { key: "provider", label: "provider", width: 220 },
  { key: "endpoint", label: "endpoint", width: 560 },
  { key: "status", label: "status", width: 240 },
  { key: "n", label: "results", numeric: true, width: 160 },
  { key: "cost", label: "cost", numeric: true, width: 160 },
];

const rows: Row[] = runs.slice(0, 6).map((r) => ({
  key: String(r.localSeq),
  cells: {
    seq: String(r.localSeq),
    provider: r.provider,
    endpoint: r.endpoint,
    status: r.status,
    n: r.nResults === null ? "" : String(r.nResults),
    cost: r.costUsd === null ? "" : usd(r.costUsd),
  },
  muted: r.nResults === 0,
}));

export const SceneLiveTrace: React.FC = () => (
  <BeatPlaceholder id="live-trace">
    <Table columns={columns} rows={rows} width={1420} />
    <Source
      file="results/demo/receipt.json"
      detail={`runs[] · ${totals.monidRuns} runs, ${totals.monidRunsZeroResults} with zero results, ${totals.monidRunsFailed} failed`}
    />
  </BeatPlaceholder>
);
