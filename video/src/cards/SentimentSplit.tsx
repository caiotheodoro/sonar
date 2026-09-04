/**
 * What the feed becomes: every mention labelled. The band the last shot
 * packed splits into three lanes, one dot at a time. No counts here — these
 * are the incumbent's categories, not its data.
 */
import React from "react";
import { BAND, DOT, LANE, RULE, dotAt, ease, laneDot, perRow } from "../motion/geometry";
import { SfxAt } from "../components/Sfx";
import { T, TYPE } from "../theme";
import { Card, useSince, type CardProps } from "./Card";

const DOTS = perRow * 6;
const LANES = ["POSITIVE", "NEUTRAL", "NEGATIVE"];
const LABEL_UP = 34;

export const SentimentSplit: React.FC<CardProps> = () => {
  const f = useSince(0);
  return (
    <Card plate={["BRAND24", "SENTIMENT"]}>
      <SfxAt src="blip" frames={LANES.map((_, i) => 4 + i * 5)} gain={0.5} />
      {LANES.map((name, lane) => (
        <div
          key={name}
          style={{
            position: "absolute",
            left: BAND.x,
            top: BAND.y - LABEL_UP + lane * (LANE.h + LANE.gap),
            fontFamily: T.mono,
            fontSize: TYPE.label,
            letterSpacing: "0.1em",
            color: f >= 4 + lane * 5 ? T.engrave : "transparent",
          }}
        >
          {name}
        </div>
      ))}
      {Array.from({ length: DOTS }, (_, i) => {
        const home = dotAt(i);
        const lane = i % LANES.length;
        const seat = laneDot(Math.floor(i / LANES.length), lane);
        const p = ease((f - 4 - lane * 5) / 14);
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: home.x + (seat.x - home.x) * p,
              top: home.y + (seat.y - home.y) * p,
              width: DOT.size,
              height: DOT.size,
              background: lane === 2 ? T.engrave : T.plate,
              opacity: lane === 1 ? 0.55 : 1,
            }}
          />
        );
      })}
      <div style={{ position: "absolute", left: RULE.x, top: RULE.y, width: RULE.w, height: 2, background: T.keyline }} />
    </Card>
  );
};
