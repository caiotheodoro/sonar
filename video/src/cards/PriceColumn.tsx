/**
 * What all of it costs: the rival columns slide into one, and the one is the
 * seat price. The column is left standing at COLUMN, which is where the next
 * shot's orange starts from.
 */
import React from "react";
import { COLUMN, RULE, ease } from "../motion/geometry";
import { Sfx } from "../components/Sfx";
import { usdWhole } from "../data/results";
import { fact } from "../data/facts";
import { RESULTS } from "../manifest";
import { displayFamily } from "../fonts";
import { T, TYPE } from "../theme";
import { Card, Label, useCountOver, useSince, type CardProps } from "./Card";

const { incumbent } = RESULTS.receipt;
const KEYWORDS = fact("brand24.keywords.team");
const COUNT = 22;

export const PriceColumn: React.FC<CardProps> = () => {
  const f = useSince(0);
  const rise = ease(f / 16);
  const shown = useCountOver(incumbent.priceUsdMonth, 0, COUNT);
  return (
    <Card plate={["BRAND24", "PRICING", "TEAM SEAT"]} source={["results/demo/receipt.json", "incumbent.price_usd_month", "incumbent.mentions_quota"]}>
      <Sfx src="stamp" at={COUNT} gain={0.6} />
      <div
        style={{
          position: "absolute",
          left: COLUMN.x,
          top: COLUMN.baseY - 620 * rise,
          width: COLUMN.w,
          height: 620 * rise,
          background: T.signal,
        }}
      />
      <div style={{ position: "absolute", left: COLUMN.x + COLUMN.w + 80, top: 330 }}>
        <div style={{ fontFamily: displayFamily, fontWeight: 900, fontSize: 330, lineHeight: 0.82, color: T.plate }}>
          {usdWhole(shown)}
        </div>
        <div style={{ marginTop: 22, display: "flex", gap: 64 }}>
          <div>
            <Label>a month, one seat</Label>
          </div>
          <div>
            <span style={{ fontFamily: T.mono, fontSize: TYPE.value, color: T.plate }}>{KEYWORDS.value}</span>{" "}
            <Label>keywords</Label>
          </div>
          <div>
            <span style={{ fontFamily: T.mono, fontSize: TYPE.value, color: T.plate }}>
              {incumbent.mentionsQuota.toLocaleString("en-US")}
            </span>{" "}
            <Label>mentions</Label>
          </div>
        </div>
      </div>
      <div style={{ position: "absolute", left: RULE.x, top: RULE.y, width: RULE.w, height: 2, background: T.plate }} />
    </Card>
  );
};
