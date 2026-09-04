/**
 * Beat 3: the receipt, itemised. Real receipt rows — label left, a dotted
 * leader, value right — printing down the tape, then the verdict (earned
 * here, not before). The status strip counts `×N` to `monid_runs` alongside
 * these rows (Main.tsx); the read-line ceremony is reserved for the ratio.
 */
import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { ReadLine } from "../components/ReadLine";
import { Source } from "../components/DataPanel";
import { fmt, usd } from "../data/results";
import { RESULTS, cueFrame } from "../manifest";
import { T, VERDICT } from "../theme";

const { totals, comparison, verdict } = RESULTS.receipt;

const Row: React.FC<{ label: string; value: string; at: number; emphasis?: boolean; colour?: string }> = ({
  label,
  value,
  at,
  emphasis,
  colour,
}) => {
  const frame = useCurrentFrame();
  const o = interpolate(frame, [at, at + 12], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div
      style={{
        display: "flex",
        alignItems: "baseline",
        gap: 14,
        padding: "9px 0",
        borderBottom: `1px solid ${T.border}`,
        opacity: o,
        transform: `translateY(${(1 - o) * 8}px)`,
      }}
    >
      <span
        style={{
          fontFamily: T.font,
          fontSize: 26,
          color: emphasis ? T.text : T.textMuted,
          fontWeight: emphasis ? 600 : 400,
          whiteSpace: "nowrap",
        }}
      >
        {label}
      </span>
      <span style={{ flex: 1, borderBottom: `1px dotted ${T.borderStrong}`, marginBottom: 6 }} />
      <span
        style={{
          fontFamily: T.mono,
          fontSize: 28,
          fontWeight: emphasis ? 700 : 500,
          color: colour ?? (emphasis ? T.accent : T.text),
        }}
      >
        {value}
      </span>
    </div>
  );
};

const STEP = 8;

export const SceneReceipt: React.FC = () => (
  <AbsoluteFill style={{ padding: "0 140px", justifyContent: "center" }}>
    <div style={{ width: 1100 }}>
      <Row label="runs" value={String(totals.monidRuns)} at={cueFrame("receipt", 0) + 0 * STEP} />
      <Row label="billed" value={String(totals.monidRunsBilled)} at={cueFrame("receipt", 0) + 1 * STEP} />
      <Row
        label="zero-result"
        value={String(totals.monidRunsZeroResults)}
        at={cueFrame("receipt", 0) + 2 * STEP}
      />
      <Row label="failed" value={String(totals.monidRunsFailed)} at={cueFrame("receipt", 0) + 3 * STEP} />
      <Row
        label="verdict"
        value={verdict}
        at={cueFrame("receipt", 0) + 4 * STEP}
        emphasis
        colour={VERDICT[verdict as keyof typeof VERDICT] ?? T.text}
      />

      <div style={{ height: 26 }} />

      <Row label="Monid, all runs" value={usd(totals.monidUsd)} at={cueFrame("receipt", 1) + 0 * STEP} />
      <Row label="the model" value={usd(totals.llmUsd)} at={cueFrame("receipt", 1) + 1 * STEP} />
      <Row label="the voice" value={usd(totals.elevenlabsUsd)} at={cueFrame("receipt", 1) + 2 * STEP} />
      <Row
        label="total, this brief"
        value={usd(totals.totalUsd)}
        at={cueFrame("receipt", 1) + 3 * STEP}
        emphasis
      />
      <Row
        label={`per month at ${comparison.briefsPerMonthAssumed} briefs`}
        value={usd(comparison.sonarUsdMonthEquiv)}
        at={cueFrame("receipt", 1) + 4 * STEP}
      />
    </div>

    <div style={{ marginTop: 56 }}>
      <ReadLine
        label="the incumbent's price, over that"
        value={comparison.ratio}
        domain={[0, Math.ceil((comparison.ratio ?? 1) / 5) * 5]}
        format={(n) => `${fmt(n)}×`}
        startFrame={cueFrame("receipt", 1) + 5 * STEP}
        width={1100}
        emphasis
      />
    </div>

    <Source
      file="results/demo/receipt.json"
      detail={`totals · comparison · verdict ${verdict}`}
    />
  </AbsoluteFill>
);
