/**
 * Beat 6: the outro. Beat 1's two read-lines, replayed verbatim — the same
 * axis, the same gesture, no arrow and no strikethrough standing in for the
 * argument. Then the repository and the hashtag.
 */
import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { ReadLine } from "../components/ReadLine";
import { usd, usdWhole } from "../data/results";
import { PUBLISHED, RESULTS, cueFrame } from "../manifest";
import { T } from "../theme";

const { incumbent, totals } = RESULTS.receipt;
const DOMAIN: [number, number] = [0, incumbent.priceUsdMonth];

export const SceneOutro: React.FC = () => {
  const frame = useCurrentFrame();
  const linksAt = cueFrame("outro", 0) + 30;
  const links = interpolate(frame, [linksAt, linksAt + 22], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <AbsoluteFill style={{ padding: "0 140px", justifyContent: "center" }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 56 }}>
        <div style={{ opacity: 0.55 }}>
          <ReadLine
            label={`${incumbent.name}, per month`}
            value={incumbent.priceUsdMonth}
            domain={DOMAIN}
            format={usdWhole}
            startFrame={cueFrame("outro", 0)}
            width={1300}
          />
        </div>
        <ReadLine
          label="replaced by this brief"
          value={totals.totalUsd}
          domain={DOMAIN}
          format={usd}
          startFrame={cueFrame("outro", 0)}
          width={1300}
          emphasis
        />
      </div>

      <div
        style={{
          opacity: links,
          transform: `translateY(${(1 - links) * 10}px)`,
          marginTop: 70,
          display: "flex",
          gap: 60,
          fontFamily: T.mono,
          fontSize: 30,
        }}
      >
        <span style={{ color: T.text }}>{PUBLISHED.code}</span>
        <span style={{ color: T.accent }}>{PUBLISHED.hashtag}</span>
      </div>
    </AbsoluteFill>
  );
};
