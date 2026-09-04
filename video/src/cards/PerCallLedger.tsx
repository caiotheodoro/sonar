/**
 * The same rows, now with what each one billed: the receipt forming, line by
 * line, to the Monid total. Nothing is estimated — every figure is the cost
 * the provider's own run listing returned.
 */
import React from "react";
import { ROW, ease } from "../motion/geometry";
import { ENDPOINT_ROWS } from "../motion/endpoints";
import { SfxAt } from "../components/Sfx";
import { usd } from "../data/results";
import { RESULTS } from "../manifest";
import { T, TYPE } from "../theme";
import { Card, Label, useCountOver, useSince, type CardProps } from "./Card";
import { rowY } from "./KeyFan";
import { Fan } from "./KeyFan";

const { totals } = RESULTS.receipt;
const STEP = 2;
const COUNT = 30;

export const PerCallLedger: React.FC<CardProps> = () => {
  const f = useSince(0);
  const total = useCountOver(totals.monidUsd, 0, COUNT);
  return (
    <Card plate={["MONID", "PER CALL"]} source={["results/demo/receipt.json", "runs[].cost_usd", "totals.monid_usd"]}>
      <SfxAt src="blip" frames={ENDPOINT_ROWS.map((_, i) => i * STEP)} gain={0.4} />
      <Fan progress={1} />
      {ENDPOINT_ROWS.map((r, i) => {
        const on = ease((f - i * STEP) / 5);
        return (
          <div
            key={r.source + r.endpoint}
            style={{
              position: "absolute",
              left: ROW.x,
              top: rowY(i) - ROW.h / 2,
              width: ROW.w,
              height: ROW.h,
              display: "flex",
              alignItems: "center",
              gap: 18,
              borderBottom: `1px solid ${T.border}`,
            }}
          >
            <span style={{ width: 260, fontFamily: T.mono, fontSize: TYPE.label, letterSpacing: "0.08em", textTransform: "uppercase", color: T.plate }}>
              {r.source}
            </span>
            <span style={{ flex: 1, fontFamily: T.mono, fontSize: 24, color: T.engrave, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {r.provider}
              {r.endpoint}
            </span>
            <span style={{ width: 130, textAlign: "right", fontFamily: T.mono, fontSize: 22, color: T.textFaint, opacity: on }}>
              {r.calls} calls
            </span>
            <span style={{ width: 150, textAlign: "right", fontFamily: T.mono, fontSize: 28, fontWeight: 700, color: T.plate, opacity: on }}>
              {usd(r.usd)}
            </span>
          </div>
        );
      })}
      <div style={{ position: "absolute", left: ROW.x + ROW.w - 380, top: rowY(ENDPOINT_ROWS.length) + 18, textAlign: "right", width: 380 }}>
        <div style={{ fontFamily: T.mono, fontWeight: 700, fontSize: 82, lineHeight: 1, color: T.signal }}>{usd(total)}</div>
        <Label>every call, this brief</Label>
      </div>
    </Card>
  );
};
