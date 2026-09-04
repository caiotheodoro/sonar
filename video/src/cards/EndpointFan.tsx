/**
 * Where the lines land: the endpoints this brief actually called, read off
 * the receipt's run rows. Same rows, same order as the ledger that follows.
 */
import React from "react";
import { ROW, ease } from "../motion/geometry";
import { ENDPOINT_ROWS } from "../motion/endpoints";
import { SfxAt } from "../components/Sfx";
import { T, TYPE } from "../theme";
import { Card, useSince, type CardProps } from "./Card";
import { Fan, rowY } from "./KeyFan";

const STEP = 2;

export const EndpointRows: React.FC<{ frame: number; showCost?: boolean; total?: React.ReactNode }> = ({ frame, showCost }) => (
  <>
    {ENDPOINT_ROWS.map((r, i) => {
      const on = ease((frame - i * STEP) / 6);
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
            opacity: on,
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
          {showCost ? null : (
            <span style={{ fontFamily: T.mono, fontSize: 22, color: T.textFaint }}>{r.results} results</span>
          )}
        </div>
      );
    })}
  </>
);

export const EndpointFan: React.FC<CardProps> = () => {
  const f = useSince(0);
  return (
    <Card plate={["MONID", "ENDPOINTS", "ONE BRIEF"]} source={["results/demo/receipt.json", "runs[].endpoint"]}>
      <SfxAt src="click" frames={ENDPOINT_ROWS.map((_, i) => i * STEP)} gain={0.45} />
      <Fan progress={1} />
      <EndpointRows frame={f} />
    </Card>
  );
};
