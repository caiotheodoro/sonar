/**
 * One key, one balance. A single point on the left throws a line to every
 * endpoint row on the right; the rows are empty here and the next shot fills
 * them in, so the fan is still on screen when the labels arrive.
 */
import React from "react";
import { KEY, ROW, ease } from "../motion/geometry";
import { ENDPOINT_ROWS } from "../motion/endpoints";
import { Sfx, SfxAt } from "../components/Sfx";
import { fact, factText } from "../data/facts";
import { displayFamily } from "../fonts";
import { T, TYPE } from "../theme";
import { Card, Label, useCountOver, useSince, type CardProps } from "./Card";

const TOOLS = fact("monid.tools");
const DRAW = 26;

export const rowY = (i: number): number => ROW.y0 + i * ROW.h + ROW.h / 2;

export const Fan: React.FC<{ progress: number }> = ({ progress }) => (
  <svg width={1920} height={1080} style={{ position: "absolute", left: 0, top: 0, pointerEvents: "none" }}>
    {ENDPOINT_ROWS.map((r, i) => {
      const p = Math.max(0, Math.min(1, progress * ENDPOINT_ROWS.length - i));
      return (
        <line
          key={r.source + r.endpoint}
          x1={KEY.x}
          y1={KEY.y}
          x2={KEY.x + (ROW.x - KEY.x) * ease(p)}
          y2={KEY.y + (rowY(i) - KEY.y) * ease(p)}
          stroke={T.keyline}
          strokeWidth={2}
        />
      );
    })}
    <circle cx={KEY.x} cy={KEY.y} r={9} fill={T.signal} />
  </svg>
);

export const KeyFan: React.FC<CardProps> = () => {
  const f = useSince(0);
  const tools = useCountOver(TOOLS.value, 0, DRAW);
  return (
    <Card plate={["MONID", "ONE KEY", "ONE BALANCE"]} source={[new URL(TOOLS.source_url).host, TOOLS.captured_at]}>
      <Sfx src="sweep" at={0} gain={0.5} />
      <SfxAt src="click" frames={ENDPOINT_ROWS.map((_, i) => Math.round((i / ENDPOINT_ROWS.length) * DRAW))} gain={0.4} />
      <Fan progress={f / DRAW} />
      <div style={{ position: "absolute", left: ROW.x + 340, top: 380, width: ROW.w - 340 }}>
        <div style={{ fontFamily: displayFamily, fontWeight: 900, fontSize: 190, lineHeight: 1, color: T.plate }}>
          {f >= DRAW ? factText(TOOLS.id) : Math.round(tools).toLocaleString("en-US")}
        </div>
        <div style={{ marginTop: 24 }}>
          <Label>tools on one balance</Label>
        </div>
        <div style={{ marginTop: 14, fontFamily: T.mono, fontSize: TYPE.label, letterSpacing: "0.08em", color: T.engrave }}>
          PAID PER CALL
        </div>
      </div>
    </Card>
  );
};
