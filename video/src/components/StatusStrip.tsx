/**
 * The instrument's status line — two edge-anchored elements, frame-locked.
 * Left: elapsed time. Right: the running `POST /v1/run` count, which flips
 * on when the Monid act starts and, once the rebuild act begins, counts up to
 * the real run total from the frozen receipt. Hidden on shots that ask
 * (`statusStrip: false`, the full-bleed stamp).
 */
import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { RESULTS } from "../manifest";
import { TIMELINE, actFrom } from "../timeline";
import { T } from "../theme";

export const StatusStrip: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const current = TIMELINE.shots.find((s) => f >= s.from && f < s.from + s.durationInFrames);
  if (current && current.shot.statusStrip === false) return null;

  const elapsed = (f / fps).toFixed(1).padStart(4, "0");
  const live = f >= actFrom("monid");
  const countFrom = actFrom("rebuild");
  const total = RESULTS.receipt.totals.monidRuns;
  const count = !live
    ? 0
    : f < countFrom
      ? 1
      : Math.round(
          interpolate(f, [countFrom, countFrom + 90], [1, total], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
        );

  const base: React.CSSProperties = {
    position: "absolute",
    top: 24,
    fontFamily: T.mono,
    fontSize: 18,
    letterSpacing: "0.04em",
    color: T.textFaint,
  };

  return (
    <>
      <div style={{ ...base, left: 64 }}>T+{elapsed}S</div>
      <div style={{ ...base, right: 64, color: live ? T.signal : T.textFaint }}>
        POST /v1/run ×{count}
      </div>
    </>
  );
};
