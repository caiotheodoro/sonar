/** Brand24 sentiment + share of voice → sonar: every value with its 95% interval, read on the line. */
import React from "react";
import { ReadLine } from "../components/ReadLine";
import { net, pct } from "../data/results";
import { RESULTS } from "../manifest";
import { T, TYPE } from "../theme";
import { Card, Label, type CardProps } from "./Card";

const { shareOfVoice, sentiment } = RESULTS.stats;
const brand = RESULTS.receipt.brand;
const sov = shareOfVoice.find((r) => r.brand === brand);
const sent = sentiment.find((r) => r.brand === brand);
if (!sov || sov.share === null || !sent || sent.net === null) {
  throw new Error(`results/demo/stats.json: the brand ${brand} must carry share and net for the rebuild card`);
}
const measured = shareOfVoice.filter((r) => r.share !== null);

export const MapSentimentSov: React.FC<CardProps> = () => (
  <Card plate={["REBUILD", "SENTIMENT", "SHARE OF VOICE"]} reproduces="sentiment and share of voice" source={["results/demo/stats.json", "share_of_voice", "sentiment", "ci95 bootstrap"]}>
    <div style={{ display: "flex", gap: 80 }}>
      <ReadLine label={`${brand}, share of voice`} value={sov.share} ci={sov.ci95} domain={[0, 0.5]} format={pct} startFrame={2} width={820} />
      <ReadLine label={`${brand}, net sentiment`} value={sent.net} ci={sent.ci95} domain={[-0.5, 0.5]} format={net} startFrame={6} width={820} />
    </div>
    <div style={{ marginTop: 56, display: "flex", gap: 64 }}>
      {measured.map((r) => (
        <div key={r.brand}>
          <Label>{r.brand}</Label>
          <div style={{ fontFamily: T.mono, fontWeight: 700, fontSize: TYPE.value, color: T.plate }}>
            {pct(r.share as number)}{" "}
            <span style={{ fontSize: TYPE.label, color: T.textFaint }}>{r.ci95 ? `[${pct(r.ci95[0])}, ${pct(r.ci95[1])}]` : ""}</span>
          </div>
        </div>
      ))}
    </div>
  </Card>
);
