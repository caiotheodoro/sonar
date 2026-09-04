/**
 * Beat 1, the first five-odd seconds: what died. Two read-lines on the same
 * axis — the incumbent's monthly list price drawn full width, then this
 * brief's measured total, which barely leaves zero. No verdict word here; it
 * is earned in the receipt beat. The camera never cuts to get here: this is
 * simply the top of the tape.
 */
import React from "react";
import { AbsoluteFill } from "remotion";
import { ReadLine } from "../components/ReadLine";
import { Source } from "../components/DataPanel";
import { usd, usdWhole } from "../data/results";
import { RESULTS, cueFrame } from "../manifest";

const { incumbent, totals } = RESULTS.receipt;
const DOMAIN: [number, number] = [0, incumbent.priceUsdMonth];

export const ScenePriceDied: React.FC = () => (
  <AbsoluteFill style={{ padding: "0 140px", justifyContent: "center" }}>
    <div style={{ display: "flex", flexDirection: "column", gap: 70 }}>
      <ReadLine
        label={`${incumbent.name}, per month`}
        value={incumbent.priceUsdMonth}
        domain={DOMAIN}
        format={usdWhole}
        startFrame={cueFrame("price-died", 0)}
        width={1500}
      />
      <ReadLine
        label="this brief, measured"
        value={totals.totalUsd}
        domain={DOMAIN}
        format={usd}
        startFrame={cueFrame("price-died", 1)}
        width={1500}
        emphasis
      />
    </div>
    <Source
      file="results/demo/receipt.json"
      detail="incumbent.price_usd_month · totals.total_usd"
    />
  </AbsoluteFill>
);
