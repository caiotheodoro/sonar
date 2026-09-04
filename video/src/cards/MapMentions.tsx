/** Brand24 mentions → sonar: fetched count and the by-source breakdown, every bar a real count. */
import React from "react";
import { RESULTS } from "../manifest";
import { T, TYPE } from "../theme";
import { Big, Card, Label, useCount, useSince, type CardProps } from "./Card";
import { SfxAt } from "../components/Sfx";
import { MOTION } from "../theme";

const { mentions } = RESULTS.receipt;
const rows = Object.entries(mentions.bySource).sort((a, b) => b[1] - a[1]);
const max = Math.max(...rows.map(([, n]) => n));

export const MapMentions: React.FC<CardProps> = () => {
  const f = useSince(0);
  const shown = Math.round(useCount(mentions.deduped, 2));
  return (
    <Card plate={["REBUILD", "MENTIONS"]} reproduces="mentions feed" source={["results/demo/receipt.json", "mentions.by_source", "mentions.deduped"]}>
      <SfxAt src="tick" frames={Array.from({ length: Math.floor(MOTION.countFrames / 2) }, (_, i) => 2 + i * 2)} gain={0.35} />
      <SfxAt src="blip" frames={rows.map((_, i) => 4 + i * 2)} gain={0.4} />
      <div style={{ display: "flex", gap: 96, alignItems: "flex-start" }}>
        <div>
          <Big size={300}>{shown}</Big>
          <div><Label>mentions, one brief, deduplicated</Label></div>
        </div>
        <div style={{ width: 900, marginTop: 12 }}>
          {rows.map(([source, n], i) => {
            const on = f >= 4 + i * 2;
            return (
              <div key={source} style={{ display: "flex", alignItems: "center", gap: 16, height: 40, opacity: on ? 1 : 0 }}>
                <span style={{ width: 230, fontFamily: T.mono, fontSize: TYPE.label, letterSpacing: "0.06em", textTransform: "uppercase", color: T.engrave }}>{source}</span>
                <div style={{ flex: 1, height: 18, background: T.shadow }}>
                  <div style={{ width: `${(n / max) * 100}%`, height: "100%", background: T.plate }} />
                </div>
                <span style={{ width: 60, textAlign: "right", fontFamily: T.mono, fontSize: 26, color: T.plate }}>{n}</span>
              </div>
            );
          })}
        </div>
      </div>
    </Card>
  );
};
