/**
 * The receipt, itemised. Real rows — label left, a dotted leader, value
 * right — printing down the plate, each read from the frozen receipt. Row
 * ids are the storyboard's vocabulary; "billed" and "zero" are separate
 * facts that overlap (a zero-result run is still billed), so no label here
 * implies a partition and the word "all" never appears.
 */
import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { Plate } from "./Plate";
import { usd } from "../data/results";
import { RESULTS, RESULTS_EMPTY } from "../manifest";
import { LAYOUT, T, TYPE, VERDICT } from "../theme";
import type { ReceiptRowId } from "../timeline/types";

const Row: React.FC<{ label: string; value: string; at: number; emphasis?: boolean; colour?: string }> = ({
  label,
  value,
  at,
  emphasis,
  colour,
}) => {
  const frame = useCurrentFrame();
  const on = frame >= at ? 1 : 0;
  return (
    <div
      style={{
        display: "flex",
        alignItems: "baseline",
        gap: 18,
        padding: "12px 0",
        borderBottom: `1px solid ${T.border}`,
        opacity: on,
      }}
    >
      <span
        style={{
          fontFamily: T.mono,
          fontSize: 30,
          letterSpacing: "0.06em",
          textTransform: "uppercase",
          color: emphasis ? T.plate : T.engrave,
          whiteSpace: "nowrap",
        }}
      >
        {label}
      </span>
      <span style={{ flex: 1, borderBottom: `1px dotted ${T.borderStrong}`, marginBottom: 8 }} />
      <span
        style={{
          fontFamily: T.mono,
          fontSize: emphasis ? 56 : TYPE.value,
          fontWeight: 700,
          color: colour ?? (emphasis ? T.signal : T.plate),
        }}
      >
        {value}
      </span>
    </div>
  );
};

const STEP = 4;

export const ReceiptRows: React.FC<{
  rows: ReceiptRowId[];
  results?: "demo" | "demo-empty";
  startFrame?: number;
  width?: number;
}> = ({ rows, results = "demo", startFrame = 2, width = 1400 }) => {
  const R = results === "demo-empty" ? RESULTS_EMPTY : RESULTS;
  const { totals, comparison, verdict, mentions, sessionId } = R.receipt;
  const row = (id: ReceiptRowId, i: number): React.ReactNode => {
    const at = startFrame + i * STEP;
    switch (id) {
      case "runs":
        return <Row key={id} label="Monid runs" value={String(totals.monidRuns)} at={at} />;
      case "billed":
        return <Row key={id} label="billed" value={String(totals.monidRunsBilled)} at={at} />;
      case "zero":
        return <Row key={id} label="came back empty, still on the receipt" value={String(totals.monidRunsZeroResults)} at={at} />;
      case "failed":
        return <Row key={id} label="failed" value={String(totals.monidRunsFailed)} at={at} />;
      case "verdict":
        return <Row key={id} label="verdict" value={verdict} at={at} emphasis colour={VERDICT[verdict as keyof typeof VERDICT] ?? T.plate} />;
      case "monid":
        return <Row key={id} label="Monid, every call" value={usd(totals.monidUsd)} at={at} />;
      case "llm":
        return <Row key={id} label="the model" value={usd(totals.llmUsd)} at={at} />;
      case "voice":
        return <Row key={id} label="the voice" value={usd(totals.elevenlabsUsd)} at={at} />;
      case "total":
        return <Row key={id} label="this brief" value={usd(totals.totalUsd)} at={at} emphasis />;
      case "monthly":
        return <Row key={id} label={`per month, ${comparison.briefsPerMonthAssumed} briefs`} value={usd(comparison.sonarUsdMonthEquiv)} at={at} />;
      case "mentions":
        return <Row key={id} label="mentions fetched" value={String(mentions.fetched)} at={at} />;
    }
  };
  return (
    <AbsoluteFill style={{ padding: LAYOUT.margin, justifyContent: "center" }}>
      <Plate segments={["RECEIPT", sessionId]} size={TYPE.label} style={{ marginBottom: 28 }} />
      <div style={{ width }}>{rows.map(row)}</div>
      <Plate segments={[`results/${results}/receipt.json`, "totals", `verdict ${verdict}`]} size={16} style={{ marginTop: 28 }} />
    </AbsoluteFill>
  );
};
