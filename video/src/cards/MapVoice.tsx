/** Brand24 reports → sonar: a spoken summary, synthesised through Monid, one line on the receipt. */
import React from "react";
import { usd } from "../data/results";
import { RESULTS } from "../manifest";
import { T, TYPE } from "../theme";
import { Big, Card, Label, useSince, type CardProps } from "./Card";
import { SfxAt } from "../components/Sfx";

const { totals, runs, verdict } = RESULTS.receipt;
const voiceRun = runs.find((r) => r.provider === "elevenlabs");
const providers = [...new Set(runs.map((r) => r.provider))];

const BARS = 48;

export const MapVoice: React.FC<CardProps> = () => {
  const f = useSince(0);
  return (
    <Card plate={["REBUILD", "REPORTS", "VOICE"]} reproduces="reports" source={["results/demo/receipt.json", "runs[provider=elevenlabs]", "totals.elevenlabs_usd"]}>
      <SfxAt src="tick" frames={Array.from({ length: 8 }, (_, i) => i * 3)} gain={0.3} />
      <div style={{ display: "flex", alignItems: "flex-end", gap: 6, height: 220, marginBottom: 40 }}>
        {Array.from({ length: BARS }, (_, i) => {
          const h = 30 + 170 * Math.abs(Math.sin(i * 0.9) * Math.cos(i * 0.37));
          return <div key={i} style={{ width: 22, height: h, background: i <= f * 2 ? T.plate : T.shadow }} />;
        })}
      </div>
      <div style={{ display: "flex", gap: 96, alignItems: "baseline" }}>
        <div>
          <Label>a spoken summary, synthesised through Monid</Label>
          <div style={{ fontFamily: T.mono, fontSize: 30, color: T.plate, marginTop: 8 }}>
            {voiceRun ? `${voiceRun.provider}${voiceRun.endpoint}` : "elevenlabs"}
          </div>
        </div>
        <div>
          <Label>the voice, on the receipt</Label>
          <div><Big size={96}>{usd(totals.elevenlabsUsd)}</Big></div>
        </div>
      </div>
      <div style={{ marginTop: 40, fontFamily: T.mono, fontSize: TYPE.label, letterSpacing: "0.06em", textTransform: "uppercase", color: T.engrave }}>
        providers on this receipt: {providers.join(" / ")} · verdict {verdict}
      </div>
    </Card>
  );
};
