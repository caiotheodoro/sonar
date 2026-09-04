/**
 * Typographic stamps. The slam: one frame of black, then the word lands from
 * 1.12× to 1× over `MOTION.slamFrames`. `killed` is the only full-bleed
 * signal-orange frame in the cut and shakes for three frames on landing.
 */
import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { displayFamily } from "../fonts";
import { LAYOUT, MOTION, T, TYPE } from "../theme";
import { ease } from "../motion/geometry";
import { Plate } from "./Plate";
import { Sfx } from "./Sfx";

const SHAKE = [0, 6, -5, 3, 0];

export const Stamp: React.FC<{
  variant: "killed" | "title" | "ratio" | "outro" | "plate";
  text: string;
  plate?: string[];
  /** Rectangle the fill grows out of, so the cut continues the last shape. */
  wipe?: { x: number; y: number; w: number; h: number };
}> = ({ variant, text, plate, wipe }) => {
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
  const grow = wipe ? ease(f / 5) : 1;
  return (
    <>
    <Sfx src={killed ? "hit" : "stamp"} at={1} gain={killed ? 1 : 0.8} />
    {killed && wipe && grow < 1 ? (
      <AbsoluteFill style={{ background: T.ink }}>
        <div
          style={{
            position: "absolute",
            left: wipe.x * (1 - grow),
            top: wipe.y * (1 - grow),
            width: wipe.w + (1920 - wipe.w) * grow,
            height: wipe.h + (1080 - wipe.h) * grow,
            background: T.signal,
          }}
        />
      </AbsoluteFill>
    ) : null}
    <AbsoluteFill
      style={{
        background: killed ? (grow < 1 ? "transparent" : T.signal) : T.ink,
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
    </>
  );
};
