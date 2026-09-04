/**
 * The instrument's status line — two edge-anchored elements, frame-locked.
 * Left: elapsed time. Right: the running `POST /v1/run` count, which flips on
 * amber when the live-trace beat starts and, once the receipt beat begins,
 * counts up to the real run total from the frozen receipt.
 */
import React from "react";
import { interpolate, useCurrentFrame, useVideoConfig } from "remotion";
import { RESULTS, from } from "../manifest";
import { T } from "../theme";

export const StatusStrip: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const elapsed = (f / fps).toFixed(1).padStart(4, "0");

  const live = f >= from(1);
  const receiptFrom = from(2);
  const total = RESULTS.receipt.totals.monidRuns;
  const count = !live
    ? 0
    : f < receiptFrom
      ? 1
      : Math.round(
          interpolate(f, [receiptFrom, receiptFrom + 90], [1, total], {
            extrapolateLeft: "clamp",
            extrapolateRight: "clamp",
          }),
        );

  const base: React.CSSProperties = {
    position: "absolute",
    top: 30,
    fontFamily: T.mono,
    fontSize: 20,
    color: T.textFaint,
  };

  return (
    <>
      <div style={{ ...base, left: 40 }}>t+{elapsed}s</div>
      <div style={{ ...base, right: 40, color: live ? T.accent : T.textFaint }}>
        POST /v1/run ×{count}
      </div>
    </>
  );
};
