/** The ratio, giant, with the monthly equivalent it rests on. */
import React from "react";
import { fmt, usd } from "../data/results";
import { RESULTS } from "../manifest";
import { displayFamily } from "../fonts";
import { T, TYPE } from "../theme";
import { Card, Label, useCount, type CardProps } from "./Card";
import { Sfx, SfxAt } from "../components/Sfx";
import { MOTION } from "../theme";

const { comparison } = RESULTS.receipt;
if (comparison.ratio === null) throw new Error("results/demo/receipt.json: comparison.ratio is null");
const RATIO = comparison.ratio;

export const Ratio: React.FC<CardProps> = () => {
  const shown = useCount(RATIO, 1);
  return (
    <Card plate={["COST", "RATIO"]} source={["results/demo/receipt.json", "comparison.ratio", "comparison.sonar_usd_month_equiv"]}>
      <SfxAt src="tick" frames={Array.from({ length: Math.floor(MOTION.countFrames / 2) }, (_, i) => 1 + i * 2)} gain={0.4} />
      <Sfx src="stamp" at={1 + MOTION.countFrames} gain={0.7} />
      <div style={{ fontFamily: displayFamily, fontWeight: 900, fontSize: 560, lineHeight: 0.82, color: T.signal, letterSpacing: "-0.01em" }}>
        {fmt(shown)}×
      </div>
      <div style={{ marginTop: 40, display: "flex", gap: 80, alignItems: "baseline" }}>
        <div>
          <Label>under the seat</Label>
        </div>
        <div>
          <Label>{comparison.briefsPerMonthAssumed} briefs a month</Label>
          <div style={{ fontFamily: T.mono, fontWeight: 700, fontSize: TYPE.headline, color: T.plate, lineHeight: 1 }}>{usd(comparison.sonarUsdMonthEquiv)}</div>
        </div>
      </div>
    </Card>
  );
};
