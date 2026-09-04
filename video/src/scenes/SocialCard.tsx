/**
 * The share card: a static 1200×630 plate for the X post and any link
 * preview, in the cut's stamp system. Same rule as every card — nothing
 * here is typed, everything comes through RESULTS.
 */
import React from "react";
import { AbsoluteFill } from "remotion";
import { Plate } from "../components/Plate";
import { fmt, usd, usdWhole } from "../data/results";
import { displayFamily } from "../fonts";
import { PUBLISHED, RESULTS } from "../manifest";
import { T } from "../theme";

const { incumbent, totals, comparison, verdict, sessionId } = RESULTS.receipt;

export const SocialCard: React.FC = () => (
  <AbsoluteFill style={{ background: T.ink, padding: 56, fontFamily: T.mono, color: T.plate, justifyContent: "space-between" }}>
    <Plate segments={["SONAR", "RECEIPT", sessionId]} size={16} />

    <div>
      <div style={{ fontFamily: displayFamily, fontWeight: 900, fontSize: 150, lineHeight: 0.85, textTransform: "uppercase", color: T.plate }}>
        Rebuilt
        <br />
        on Monid.
      </div>
      <div style={{ display: "flex", gap: 56, alignItems: "baseline", marginTop: 28 }}>
        <div>
          <Plate segments={[`${incumbent.name}`, "MO"]} size={14} />
          <div style={{ fontSize: 56, fontWeight: 700, lineHeight: 1.1, color: T.engrave }}>{usdWhole(incumbent.priceUsdMonth)}</div>
        </div>
        <div>
          <Plate segments={["ONE BRIEF", "MEASURED"]} size={14} />
          <div style={{ fontSize: 56, fontWeight: 700, lineHeight: 1.1, color: T.signal }}>{usd(totals.totalUsd)}</div>
        </div>
        <div>
          <Plate segments={[`${comparison.briefsPerMonthAssumed} BRIEFS`, "MO"]} size={14} />
          <div style={{ fontSize: 56, fontWeight: 700, lineHeight: 1.1, color: T.plate }}>
            {comparison.ratio !== null ? `${fmt(comparison.ratio)}×` : ""}
          </div>
        </div>
      </div>
    </div>

    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
      <Plate segments={[PUBLISHED.code, PUBLISHED.hashtag]} size={20} />
      <Plate segments={["VERDICT", verdict]} size={14} />
    </div>
  </AbsoluteFill>
);
