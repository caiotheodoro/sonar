/**
 * The only way a third-party number reaches the screen: the fact's display
 * value, its label, and the host it was read from. Mono, plate-white figure.
 */
import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { fact, factHost, factText } from "../data/facts";
import { MOTION, T, TYPE } from "../theme";

export const FactChip: React.FC<{ id: string; startFrame?: number; signal?: boolean }> = ({ id, startFrame = MOTION.scanFrames, signal = false }) => {
  const frame = useCurrentFrame();
  const o = frame >= startFrame ? 1 : 0;
  const f = fact(id);
  return (
    <div style={{ display: "flex", alignItems: "baseline", gap: 18, opacity: o, fontFamily: T.mono }}>
      <span style={{ fontSize: TYPE.value, fontWeight: 700, color: signal ? T.signal : T.plate, lineHeight: 1 }}>{factText(id)}</span>
      <span style={{ fontSize: TYPE.label, color: T.engrave, letterSpacing: "0.08em", textTransform: "uppercase" }}>
        {f.label}
      </span>
      <span style={{ fontSize: 16, color: T.textFaint }}>{factHost(id)} · {f.captured_at}</span>
    </div>
  );
};
