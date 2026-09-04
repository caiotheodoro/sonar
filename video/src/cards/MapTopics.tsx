/** Brand24 topics / AI insights → sonar: named topics from the digest, and the citations every answer opens. */
import React from "react";
import { RESULTS } from "../manifest";
import { T, TYPE } from "../theme";
import { Card, Label, useSince, type CardProps } from "./Card";
import { SfxAt } from "../components/Sfx";

const { topics, topMentions, coverageGaps } = RESULTS.digest;
const top = [...topics].sort((a, b) => b.n - a.n).slice(0, 6);
const cites = topMentions.slice(0, 2);

export const MapTopics: React.FC<CardProps> = () => {
  const f = useSince(0);
  return (
    <Card plate={["REBUILD", "TOPICS", "CITATIONS"]} reproduces="AI insights and topics" source={["results/demo/digest.json", "topics", "top_mentions", "coverage_gaps"]}>
      <SfxAt src="blip" frames={top.map((_, i) => 2 + i * 2)} gain={0.4} />
      <SfxAt src="click" frames={cites.map((_, i) => 8 + i * 4)} gain={0.6} />
      <div style={{ display: "flex", gap: 96 }}>
        <div style={{ width: 900 }}>
          <Label>topics, named by the model, counted by the receipt</Label>
          {top.map((t, i) => (
            <div key={t.topicId} style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", borderBottom: `1px solid ${T.border}`, padding: "10px 0", opacity: f >= 2 + i * 2 ? 1 : 0 }}>
              <span style={{ fontFamily: T.mono, fontSize: 30, color: T.plate }}>{t.name}</span>
              <span style={{ fontFamily: T.mono, fontSize: 30, color: T.engrave }}>{t.n}</span>
            </div>
          ))}
        </div>
        <div style={{ width: 640 }}>
          <Label>every answer cites a real post</Label>
          {cites.map((m, i) => (
            <div key={m.mentionId} style={{ marginTop: 18, border: `1px solid ${T.keyline}`, padding: "14px 18px", opacity: f >= 8 + i * 4 ? 1 : 0 }}>
              <div style={{ fontFamily: T.mono, fontSize: TYPE.label, letterSpacing: "0.06em", textTransform: "uppercase", color: T.signal }}>
                [{i + 1}] {m.source}
              </div>
              <div style={{ fontFamily: T.mono, fontSize: 20, color: T.plate, marginTop: 8, lineHeight: 1.4, overflow: "hidden", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical" }}>
                “{m.quote}”
              </div>
              <div style={{ fontFamily: T.mono, fontSize: 16, color: T.textFaint, marginTop: 8, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{m.url}</div>
            </div>
          ))}
          {coverageGaps[0] ? (
            <div style={{ marginTop: 18, fontFamily: T.mono, fontSize: TYPE.label, color: T.textFaint, letterSpacing: "0.06em", textTransform: "uppercase", opacity: f >= 18 ? 1 : 0 }}>
              {coverageGaps[0].source} / {coverageGaps[0].reason} / said on the receipt
            </div>
          ) : null}
        </div>
      </div>
    </Card>
  );
};
