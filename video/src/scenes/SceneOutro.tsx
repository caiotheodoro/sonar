/**
 * Beat 6: the outro. Repository URL and the `#monid` hashtag, with the price
 * that died and the measured cost beside it one last time.
 */
import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { BeatPlaceholder } from "../components/BeatPlaceholder";
import { usd, usdWhole } from "../data/results";
import { PUBLISHED, RESULTS } from "../manifest";
import { T } from "../theme";

const { incumbent, totals } = RESULTS.receipt;

export const SceneOutro: React.FC = () => {
  const frame = useCurrentFrame();
  const links = interpolate(frame, [20, 42], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return (
    <BeatPlaceholder id="outro">
      <div style={{ fontFamily: T.mono, fontSize: 44, color: T.text }}>
        {usdWhole(incumbent.priceUsdMonth)} a month, replaced for {usd(totals.totalUsd)}.
      </div>
      <div style={{ opacity: links, marginTop: 60, display: "flex", gap: 60, fontFamily: T.mono, fontSize: 30 }}>
        <span style={{ color: T.text }}>{PUBLISHED.code}</span>
        <span style={{ color: T.accent }}>{PUBLISHED.hashtag}</span>
      </div>
    </BeatPlaceholder>
  );
};
