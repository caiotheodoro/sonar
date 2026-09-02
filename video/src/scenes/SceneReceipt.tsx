/**
 * Beat 3: the receipt scroll. Totals and the comparison block, read off the
 * receipt. The final scene scrolls the rendered receipt from
 * public/casts/receipt.cast; the figures here are what that scroll must show.
 */
import React from "react";
import { BeatPlaceholder } from "../components/BeatPlaceholder";
import { Column, Row, Source, Table } from "../components/DataPanel";
import { fmt, usd } from "../data/results";
import { RESULTS } from "../manifest";

const { totals, comparison, mentions, verdict } = RESULTS.receipt;

const columns: Column[] = [
  { key: "what", label: "line", width: 620 },
  { key: "value", label: "value", numeric: true, width: 260 },
];

const rows: Row[] = [
  { key: "monid", cells: { what: "Monid, all runs incl. failed and empty", value: usd(totals.monidUsd) } },
  { key: "llm", cells: { what: "LLM labelling, embeddings, narration", value: usd(totals.llmUsd) } },
  { key: "voice", cells: { what: "ElevenLabs voice", value: usd(totals.elevenlabsUsd) } },
  { key: "total", cells: { what: "total, this brief", value: usd(totals.totalUsd) }, emphasis: true },
  { key: "month", cells: { what: `per month at ${comparison.briefsPerMonthAssumed} briefs`, value: usd(comparison.sonarUsdMonthEquiv) } },
  { key: "ratio", cells: { what: "incumbent price over that", value: comparison.ratio === null ? "n/a" : `${fmt(comparison.ratio)}×` } },
  { key: "mentions", cells: { what: "mentions fetched / deduped / labelled", value: `${mentions.fetched} / ${mentions.deduped} / ${mentions.labelled}` } },
];

export const SceneReceipt: React.FC = () => (
  <BeatPlaceholder id="receipt">
    <Table columns={columns} rows={rows} width={900} />
    <Source file="results/demo/receipt.json" detail={`totals · comparison · mentions · verdict ${verdict}`} />
  </BeatPlaceholder>
);
