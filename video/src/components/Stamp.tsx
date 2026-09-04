/**
 * Typographic stamps. The slam: one frame of black, then the word lands from
 * 1.12× to 1× over `MOTION.slamFrames`. `killed` is the only full-bleed
 * signal-orange frame in the cut and shakes for three frames on landing.
 */
import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { displayFamily } from "../fonts";
import { LAYOUT, MOTION, T, TYPE } from "../theme";
import { Plate } from "./Plate";

const SHAKE = [0, 6, -5, 3, 0];

export const Stamp: React.FC<{
  variant: "killed" | "title" | "ratio" | "outro" | "plate";
  text: string;
  plate?: string[];
}> = ({ variant, text, plate }) => {
  const frame = useCurrentFrame();
  if (frame === 0 && variant !== "plate") return <AbsoluteFill style={{ background: T.ink }} />;
  const f = frame - 1;
  const s = interpolate(f, [0, MOTION.slamFrames], [1.12, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const shake = variant === "killed" ? (SHAKE[Math.min(f, SHAKE.length - 1)] ?? 0) : 0;

  if (variant === "plate") {
    return (
      <AbsoluteFill style={{ background: T.ink, padding: LAYOUT.margin, justifyContent: "flex-end" }}>
        <Plate segments={[text, ...(plate ?? [])]} size={56} typewriter cps={0.5} />
      </AbsoluteFill>
    );
  }

  const killed = variant === "killed";
  return (
    <AbsoluteFill
      style={{
        background: killed ? T.signal : T.ink,
        transform: `translate(${shake}px, ${-shake / 2}px)`,
        padding: LAYOUT.margin,
        justifyContent: "space-between",
      }}
    >
      <div
        style={{
          fontFamily: displayFamily,
          fontWeight: 900,
          fontSize: killed ? 640 : TYPE.stamp,
          lineHeight: 0.82,
          letterSpacing: killed ? "-0.01em" : "0.01em",
          color: killed ? T.ink : T.plate,
          transform: `scale(${s})`,
          transformOrigin: "0% 100%",
          marginTop: "auto",
          textTransform: "uppercase",
        }}
      >
        {text}
      </div>
      {plate ? (
        <div style={{ marginTop: 24 }}>
          <Plate
            segments={plate}
            size={TYPE.label}
            style={killed ? { color: T.ink } : undefined}
          />
        </div>
      ) : null}
    </AbsoluteFill>
  );
};
