/**
 * The feed: mentions arriving. One dot is one mention; they fly in from the
 * left and pack into the band that the next two shots take apart. The count
 * is the incumbent's own monthly quota, read from the receipt.
 */
import React from "react";
import { BAND, DOT, RULE, dotAt, ease, perRow } from "../motion/geometry";
import { SfxAt } from "../components/Sfx";
import { RESULTS } from "../manifest";
import { displayFamily } from "../fonts";
import { T } from "../theme";
import { Card, Label, useSince, type CardProps } from "./Card";

const QUOTA = RESULTS.receipt.incumbent.mentionsQuota;
const DOTS = perRow * 6;
const FILL = 44;

export const MentionStream: React.FC<CardProps> = () => {
  const f = useSince(0);
  const landed = Math.floor(DOTS * ease(f / FILL));
  const shown = Math.round(QUOTA * ease(f / FILL));
  return (
    <Card plate={["BRAND24", "MENTIONS"]} source={["results/demo/receipt.json", "incumbent.mentions_quota"]}>
      <SfxAt src="tick" frames={Array.from({ length: 14 }, (_, i) => 1 + i * 3)} gain={0.28} />
      <div style={{ position: "absolute", left: BAND.x, top: 230 }}>
        <div style={{ fontFamily: displayFamily, fontWeight: 900, fontSize: 170, lineHeight: 1, color: T.plate }}>
          {shown.toLocaleString("en-US")}
        </div>
        <div style={{ marginTop: 16 }}>
          <Label>mentions a month, on the Team seat</Label>
        </div>
      </div>
      {Array.from({ length: landed }, (_, i) => {
        const p = dotAt(i);
        const born = (i / DOTS) * FILL;
        const travel = ease((f - born) / 8);
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: p.x - (1 - travel) * 900,
              top: p.y,
              width: DOT.size,
              height: DOT.size,
              background: T.plate,
              opacity: travel,
            }}
          />
        );
      })}
      <div style={{ position: "absolute", left: RULE.x, top: RULE.y, width: RULE.w, height: 2, background: T.keyline }} />
    </Card>
  );
};
