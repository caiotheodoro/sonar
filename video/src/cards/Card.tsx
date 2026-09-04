/** Shared card scaffolding: the plate, a title, a body, and the source line. */
import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { Plate } from "../components/Plate";
import { displayFamily } from "../fonts";
import { LAYOUT, MOTION, T, TYPE } from "../theme";

export interface CardProps {
  durationInFrames: number;
}

export const Card: React.FC<{
  plate: string[];
  title?: string;
  /** The Brand24 feature this card reproduces; drawn engraved above the title. */
  reproduces?: string;
  source?: string[];
  children?: React.ReactNode;
  align?: "center" | "start";
}> = ({ plate, title, reproduces, source, children, align = "center" }) => (
  <AbsoluteFill style={{ padding: LAYOUT.margin, justifyContent: align === "center" ? "center" : "flex-start", background: T.ink }}>
    <Plate segments={plate} size={TYPE.label} style={{ position: "absolute", top: LAYOUT.margin + 24, left: LAYOUT.margin }} />
    {reproduces ? (
      <div style={{ fontFamily: T.mono, fontSize: TYPE.label, letterSpacing: "0.08em", color: T.engrave, marginBottom: 12 }}>
        BRAND24 <span style={{ color: T.textFaint }}>/</span> {reproduces.toUpperCase()}{" "}
        <span style={{ color: T.signal }}>→</span> SONAR ON MONID
      </div>
    ) : null}
    {title ? (
      <div
        style={{
          fontFamily: displayFamily,
          fontWeight: 900,
          fontSize: TYPE.headline,
          lineHeight: 0.9,
          color: T.plate,
          textTransform: "uppercase",
          marginBottom: 36,
        }}
      >
        {title}
      </div>
    ) : null}
    {children}
    {source ? (
      <Plate segments={source} size={16} style={{ position: "absolute", bottom: LAYOUT.margin, left: LAYOUT.margin }} />
    ) : null}
  </AbsoluteFill>
);

/** Frames since `at`, clamped at 0; stagger helper. */
export const useSince = (at: number): number => Math.max(0, useCurrentFrame() - at);

/** A figure counting up over `frames`, eased. */
export const useCountOver = (target: number, at: number, frames: number): number => {
  const f = useSince(at);
  return target * (1 - Math.pow(1 - Math.min(1, f / frames), 3));
};

/** A figure counting up over MOTION.countFrames. */
export const useCount = (target: number, at = 0): number => {
  const f = useSince(at);
  const p = Math.min(1, f / MOTION.countFrames);
  return target * (1 - Math.pow(1 - p, 3));
};

export const Big: React.FC<{ children: React.ReactNode; signal?: boolean; size?: number }> = ({ children, signal, size = TYPE.headline }) => (
  <span style={{ fontFamily: T.mono, fontWeight: 700, fontSize: size, lineHeight: 1, color: signal ? T.signal : T.plate }}>{children}</span>
);

export const Label: React.FC<{ children: React.ReactNode; style?: React.CSSProperties }> = ({ children, style }) => (
  <span style={{ fontFamily: T.mono, fontSize: TYPE.label, letterSpacing: "0.08em", textTransform: "uppercase", color: T.engrave, ...style }}>{children}</span>
);
