/** One brief: the brand, its competitors, the window, the sources. */
import React from "react";
import { RESULTS } from "../manifest";
import { T, TYPE } from "../theme";
import { displayFamily } from "../fonts";
import { Card, Label, useSince, type CardProps } from "./Card";
import { SfxAt } from "../components/Sfx";

const { brand, competitors, windowDays, sources, sessionId } = RESULTS.receipt;

export const Brief: React.FC<CardProps> = () => {
  const f = useSince(0);
  return (
    <Card plate={["BRIEF", sessionId]} source={["results/demo/receipt.json", "query"]}>
      <SfxAt src="click" frames={competitors.map((_, i) => 3 + i * 2)} gain={0.6} />
      <SfxAt src="tick" frames={sources.map((_, i) => 10 + i)} gain={0.35} />
      <div style={{ display: "flex", alignItems: "baseline", gap: 40 }}>
        <span style={{ fontFamily: displayFamily, fontWeight: 900, fontSize: 260, lineHeight: 0.85, color: T.plate, textTransform: "uppercase" }}>
          {brand}
        </span>
        <span style={{ fontFamily: T.mono, fontSize: TYPE.value, color: T.engrave }}>vs</span>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {competitors.map((c, i) => (
            <span key={c} style={{ fontFamily: T.mono, fontWeight: 700, fontSize: 56, color: f >= 3 + i * 2 ? T.plate : "transparent", textTransform: "uppercase" }}>
              {c}
            </span>
          ))}
        </div>
      </div>
      <div style={{ marginTop: 48, display: "flex", gap: 72 }}>
        <div>
          <Label>window</Label>
          <div style={{ fontFamily: T.mono, fontWeight: 700, fontSize: 72, color: T.plate, lineHeight: 1 }}>{windowDays} DAYS</div>
        </div>
        <div>
          <Label>sources</Label>
          <div style={{ fontFamily: T.mono, fontWeight: 700, fontSize: 72, color: T.plate, lineHeight: 1 }}>{sources.length}</div>
        </div>
      </div>
      <div style={{ marginTop: 28, display: "flex", flexWrap: "wrap", gap: 12 }}>
        {sources.map((s, i) => (
          <span
            key={s}
            style={{
              fontFamily: T.mono,
              fontSize: TYPE.label,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              color: T.plate,
              border: `1px solid ${T.keyline}`,
              padding: "8px 14px",
              opacity: f >= 10 + i ? 1 : 0,
            }}
          >
            {s}
          </span>
        ))}
      </div>
    </Card>
  );
};
