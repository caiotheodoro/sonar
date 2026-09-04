/**
 * The specimen frame every screenshot (and the one terminal) sits in: a 1px
 * plate keyline, four crosshair registration marks, a faint scanline overlay,
 * and the plate beneath. The reveal is the cut's one motion signature: a
 * 2px signal line sweeps top to bottom over `MOTION.scanFrames`, and the
 * image exists only above it.
 */
import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { LAYOUT, MOTION, T, TYPE } from "../theme";
import { Plate } from "./Plate";
import { Sfx } from "./Sfx";

export const SPECIMEN = {
  x: LAYOUT.margin,
  y: LAYOUT.margin + 24,
  w: 1920 - LAYOUT.margin * 2,
  h: 1080 - LAYOUT.margin * 2 - 24 - 56,
} as const;

const Cross: React.FC<{ x: number; y: number }> = ({ x, y }) => (
  <svg width={26} height={26} style={{ position: "absolute", left: x - 13, top: y - 13 }}>
    <line x1={13} y1={0} x2={13} y2={26} stroke={T.plate} strokeWidth={1} />
    <line x1={0} y1={13} x2={26} y2={13} stroke={T.plate} strokeWidth={1} />
  </svg>
);

export const Specimen: React.FC<{
  children: React.ReactNode;
  plate?: string[];
  scan?: boolean;
  /** Right-aligned content on the plate row (fact chips). */
  aside?: React.ReactNode;
}> = ({ children, plate, scan = true, aside }) => {
  const frame = useCurrentFrame();
  const p = scan
    ? interpolate(frame, [0, MOTION.scanFrames], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" })
    : 1;
  const revealed = p * SPECIMEN.h;
  return (
    <>
      {scan ? <Sfx src="sweep" at={0} gain={0.35} /> : null}
      <div
        style={{
          position: "absolute",
          left: SPECIMEN.x,
          top: SPECIMEN.y,
          width: SPECIMEN.w,
          height: SPECIMEN.h,
          background: T.shadow,
          border: `1px solid ${T.keyline}`,
          overflow: "hidden",
          boxSizing: "border-box",
        }}
      >
        <div style={{ position: "absolute", inset: 0, clipPath: `inset(0 0 ${SPECIMEN.h - revealed}px 0)` }}>{children}</div>
        {/* scanlines */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            pointerEvents: "none",
            backgroundImage: "repeating-linear-gradient(0deg, rgba(0,0,0,0.12) 0px, rgba(0,0,0,0.12) 1px, transparent 1px, transparent 3px)",
          }}
        />
        {p < 1 ? (
          <div style={{ position: "absolute", left: 0, right: 0, top: revealed - 1, height: 2, background: T.signal }} />
        ) : null}
      </div>
      <Cross x={SPECIMEN.x} y={SPECIMEN.y} />
      <Cross x={SPECIMEN.x + SPECIMEN.w} y={SPECIMEN.y} />
      <Cross x={SPECIMEN.x} y={SPECIMEN.y + SPECIMEN.h} />
      <Cross x={SPECIMEN.x + SPECIMEN.w} y={SPECIMEN.y + SPECIMEN.h} />
      <div
        style={{
          position: "absolute",
          left: SPECIMEN.x,
          right: LAYOUT.margin,
          top: SPECIMEN.y + SPECIMEN.h + 22,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
        }}
      >
        {plate ? <Plate segments={plate} size={TYPE.label} /> : <span />}
        {aside}
      </div>
    </>
  );
};
