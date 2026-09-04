/** The verdict, stamped over the receipt's own rows. */
import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { ReceiptRows } from "../components/ReceiptRows";
import { RESULTS } from "../manifest";
import { displayFamily } from "../fonts";
import { MOTION, T } from "../theme";
import type { CardProps } from "./Card";
import { Sfx } from "../components/Sfx";

const { verdict } = RESULTS.receipt;

export const Reconciled: React.FC<CardProps> = () => {
  const f = useCurrentFrame();
  const at = 14;
  const s = interpolate(f, [at, at + MOTION.slamFrames], [1.3, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return (
    <AbsoluteFill>
      <Sfx src="stamp" at={at} gain={0.9} />
      <ReceiptRows rows={["runs", "billed", "failed", "mentions", "total"]} width={740} />
      {f >= at ? (
        <div
          style={{
            position: "absolute",
            right: 64,
            top: 330,
            fontFamily: displayFamily,
            fontWeight: 900,
            fontSize: 150,
            lineHeight: 0.85,
            color: T.signal,
            border: `8px solid ${T.signal}`,
            padding: "10px 28px 0",
            transform: `rotate(-8deg) scale(${s})`,
            textTransform: "uppercase",
          }}
        >
          {verdict}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
