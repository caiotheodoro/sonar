/**
 * And what the labels become: share of voice, a brand against its rivals.
 * The lanes stand up into columns. Still no numbers — the incumbent's shape,
 * not its readings; sonar's own figures come later, with intervals.
 */
import React from "react";
import { BAND, RULE, ease } from "../motion/geometry";
import { SfxAt } from "../components/Sfx";
import { T, TYPE } from "../theme";
import { Card, useSince, type CardProps } from "./Card";

const BARS = [
  { label: "YOUR BRAND", h: 1.0, signal: true },
  { label: "RIVAL", h: 0.72, signal: false },
  { label: "RIVAL", h: 0.55, signal: false },
  { label: "RIVAL", h: 0.34, signal: false },
];
const W = 300;
const GAP = 92;
const TALL = 650;

export const ShareBars: React.FC<CardProps> = () => {
  const f = useSince(0);
  return (
    <Card plate={["BRAND24", "SHARE OF VOICE"]}>
      <SfxAt src="blip" frames={BARS.map((_, i) => 2 + i * 4)} gain={0.5} />
      {BARS.map((b, i) => {
        const grow = ease((f - 2 - i * 4) / 12);
        const h = TALL * b.h * grow;
        return (
          <React.Fragment key={i}>
            <div
              style={{
                position: "absolute",
                left: BAND.x + i * (W + GAP),
                top: RULE.y - h,
                width: W,
                height: h,
                background: b.signal ? T.plate : T.engrave,
              }}
            />
            <div
              style={{
                position: "absolute",
                left: BAND.x + i * (W + GAP),
                top: RULE.y + 20,
                fontFamily: T.mono,
                fontSize: TYPE.label,
                letterSpacing: "0.1em",
                color: grow > 0.3 ? T.engrave : "transparent",
              }}
            >
              {b.label}
            </div>
          </React.Fragment>
        );
      })}
      <div style={{ position: "absolute", left: RULE.x, top: RULE.y, width: RULE.w, height: 2, background: T.plate }} />
    </Card>
  );
};
