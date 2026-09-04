/**
 * The one terminal shot: the real `sonar run --trace` cast, framed as a
 * specimen, ramped so the run's first seconds fill a bar. `castFromMs` opens
 * the replay mid-run; the ×speed badge and clock stay on screen so what was
 * compressed is said.
 */
import React from "react";
import { AbsoluteFill } from "remotion";
import { TerminalCast } from "../components/TerminalCast";
import { Specimen } from "../components/Specimen";
import { FPS } from "../manifest";

export const CastShot: React.FC<{
  src: "run_trace" | "ask" | "empty_run";
  speed?: number;
  rows?: number;
  castFromMs?: number;
}> = ({ src, speed = 1, rows = 16, castFromMs = 0 }) => {
  const startFrame = -Math.round(((castFromMs / 1000) * FPS) / speed);
  return (
    <AbsoluteFill>
      <Specimen plate={["SONAR", "RUN", "TRACE"]} scan>
        <div style={{ padding: 8 }}>
          <TerminalCast src={src} speed={speed} rows={rows} fontSize={19} startFrame={startFrame} />
        </div>
      </Specimen>
    </AbsoluteFill>
  );
};
