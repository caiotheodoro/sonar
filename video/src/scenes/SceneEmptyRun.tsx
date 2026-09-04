/**
 * Beat 5: it can't be talked into a story. Zephyrium Bank (results/demo-empty
 * — RESULTS_EMPTY): zero mentions, every estimate abstains, and the receipt
 * still reconciles and bills all nine runs. Then the one number this whole
 * pipeline can be wrong about — its own label audit — read the same way any
 * other measured value is, landing visibly short of the bar this repo set
 * for itself (src/sonar/config.py H3_MIN_AGREEMENT, via repo-facts.json).
 */
import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { ReadLine } from "../components/ReadLine";
import { TerminalCast } from "../components/TerminalCast";
import { Source } from "../components/DataPanel";
import { RESULTS, RESULTS_EMPTY, cueFrame } from "../manifest";
import { T } from "../theme";
import repoFacts from "../data/repo-facts.json";

const { mentions, totals, verdict, audit } = RESULTS_EMPTY.receipt;
const { abstentions } = RESULTS_EMPTY.digest;
const demoAudit = RESULTS.receipt.audit;

/** "0.84", never the compact-fmt's leading-dot form — this is the hero number. */
const twoDp = (n: number): string => n.toFixed(2);

const Line: React.FC<{ children: React.ReactNode; at: number }> = ({ children, at }) => {
  const frame = useCurrentFrame();
  const o = interpolate(frame, [at, at + 12], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <div
      style={{
        opacity: o,
        transform: `translateY(${(1 - o) * 8}px)`,
        fontFamily: T.mono,
        fontSize: 26,
        color: T.text,
        marginBottom: 9,
      }}
    >
      {children}
    </div>
  );
};

export const SceneEmptyRun: React.FC = () => (
  <AbsoluteFill style={{ padding: "70px 140px 0" }}>
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
      <div style={{ minWidth: 560 }}>
        <Line at={cueFrame("empty-run", 0) + 0}>
          mentions fetched <span style={{ color: T.accent, fontWeight: 700 }}>{mentions.fetched}</span>
        </Line>
        <Line at={cueFrame("empty-run", 0) + 8}>
          verdict <span style={{ color: T.text, fontWeight: 700 }}>{verdict}</span>
        </Line>
        <Line at={cueFrame("empty-run", 0) + 16}>{totals.monidRuns} runs, all billed</Line>
        <Line at={cueFrame("empty-run", 0) + 24}>
          {abstentions.length} estimate{abstentions.length === 1 ? "" : "s"} abstained
        </Line>
      </div>

      <ReadLine
        label="our own label audit"
        value={demoAudit.agreement}
        domain={[0, 1]}
        format={twoDp}
        startFrame={cueFrame("empty-run", 1)}
        width={560}
        mark={{ value: repoFacts.auditBar, label: `bar ${twoDp(repoFacts.auditBar)}` }}
      />
    </div>

    <div style={{ marginTop: 30, maxWidth: 1600 }}>
      <TerminalCast
        src="empty_run"
        speed={1.8}
        rows={9}
        fontSize={18}
        startFrame={cueFrame("empty-run", 0) + 30}
      />
    </div>

    <Source
      file="results/demo-empty/*.json"
      detail={`mentions.fetched · audit ${audit.agreement ?? "n/a"} · results/demo/receipt.json audit.agreement`}
    />
  </AbsoluteFill>
);
