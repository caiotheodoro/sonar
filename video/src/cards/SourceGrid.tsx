/**
 * What social listening is: a lot of places, watched at once. Source names
 * strike on one after another over the rule the opening plate left behind,
 * while the count of sources the incumbent advertises runs up beside them.
 */
import React from "react";
import { RULE, ease } from "../motion/geometry";
import { SfxAt } from "../components/Sfx";
import { fact } from "../data/facts";
import { displayFamily } from "../fonts";
import { T, TYPE } from "../theme";
import { Card, Label, useSince, type CardProps } from "./Card";

/** The places Brand24's own home page lists (public/shots/brand24-home.png). */
const PLACES = [
  "SOCIAL MEDIA", "NEWS", "BLOGS", "VIDEOS", "FORUMS",
  "PODCASTS", "REVIEWS", "PHOTOS", "NEWSLETTERS", "AND MORE",
];
const STEP = 3;
const SOURCES = fact("brand24.sources");
const MILLIONS = SOURCES.value / 1_000_000;

export const SourceGrid: React.FC<CardProps> = () => {
  const f = useSince(0);
  const shown = MILLIONS * ease(f / 40);
  return (
    <Card plate={["BRAND24", "SOCIAL LISTENING"]} source={[new URL(SOURCES.source_url).host, SOURCES.captured_at]}>
      <SfxAt src="tick" frames={PLACES.map((_, i) => 2 + i * STEP)} gain={0.45} />
      <div style={{ display: "flex", alignItems: "flex-end", gap: 90 }}>
        <div>
          <div style={{ fontFamily: displayFamily, fontWeight: 900, fontSize: 300, lineHeight: 0.82, color: T.plate }}>
            {shown.toFixed(0)}
          </div>
          <div style={{ marginTop: 18 }}>
            <Label>million sources, watched</Label>
          </div>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", width: 980, gap: "14px 28px", paddingBottom: 18 }}>
          {PLACES.map((p, i) => (
            <span
              key={p}
              style={{
                fontFamily: T.mono,
                fontSize: TYPE.value,
                letterSpacing: "0.04em",
                color: f >= 2 + i * STEP ? T.plate : "transparent",
                borderBottom: `2px solid ${f >= 2 + i * STEP ? T.keyline : "transparent"}`,
              }}
            >
              {p}
            </span>
          ))}
        </div>
      </div>
      <div style={{ position: "absolute", left: RULE.x, top: RULE.y, width: RULE.w * ease(f / 20), height: 2, background: T.plate }} />
    </Card>
  );
};
