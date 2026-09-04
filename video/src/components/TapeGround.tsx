/**
 * The one dark surface the whole video rides on: near-black, a faint vertical
 * amber column rule every 64px (a sonar-waterfall / receipt-column texture),
 * and a soft top-and-bottom vignette so the tape reads as a strip rather than
 * a filled screen. Frame-locked — sits behind `<Tape>`, does not move.
 */
import React from "react";
import { AbsoluteFill } from "remotion";
import { T } from "../theme";

export const TapeGround: React.FC = () => (
  <AbsoluteFill style={{ backgroundColor: T.bg }}>
    <AbsoluteFill
      style={{
        backgroundImage: `linear-gradient(90deg, rgba(242,168,59,0.045) 1px, transparent 1px)`,
        backgroundSize: `64px 100%`,
      }}
    />
    <AbsoluteFill
      style={{
        background: `linear-gradient(to bottom, ${T.bg} 0%, transparent 14%, transparent 86%, ${T.bg} 100%)`,
      }}
    />
  </AbsoluteFill>
);
