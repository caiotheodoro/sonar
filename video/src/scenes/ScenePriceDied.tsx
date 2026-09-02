/**
 * Beat 1, the first five seconds: what died. The incumbent's monthly list
 * price on the left, the receipt's measured total on the right, both read off
 * results/demo/receipt.json. The hackathon requires exactly this pairing on
 * screen; it is the first thing a judge sees.
 */
import React from "react";
import { BeatPlaceholder } from "../components/BeatPlaceholder";
import { Source } from "../components/DataPanel";
import { usd, usdWhole } from "../data/results";
import { RESULTS } from "../manifest";
import { T, VERDICT } from "../theme";

const { incumbent, totals, verdict } = RESULTS.receipt;

const Figure: React.FC<{ label: string; value: string; colour: string }> = ({
  label,
  value,
  colour,
}) => (
  <div style={{ flex: 1 }}>
    <div style={{ fontFamily: T.font, fontSize: 28, color: T.textMuted }}>{label}</div>
    <div
      style={{
        fontFamily: T.mono,
        fontSize: 140,
        fontWeight: 700,
        letterSpacing: "-0.03em",
        lineHeight: 1,
        color: colour,
        marginTop: 12,
      }}
    >
      {value}
    </div>
  </div>
);

export const ScenePriceDied: React.FC = () => (
  <BeatPlaceholder id="price-died">
    <div style={{ display: "flex", gap: 80, alignItems: "flex-end", width: 1600 }}>
      <Figure label={`${incumbent.name}, per month`} value={usdWhole(incumbent.priceUsdMonth)} colour={T.textFaint} />
      <Figure label="this brief, measured" value={usd(totals.totalUsd)} colour={VERDICT.RECONCILED} />
    </div>
    <Source file="results/demo/receipt.json" detail={`incumbent.price_usd_month · totals.total_usd · verdict ${verdict}`} />
  </BeatPlaceholder>
);
