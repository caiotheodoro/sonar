/**
 * Beat 2: the live POST /v1/run trace. Replays public/casts/run_trace.cast
 * byte for byte — a fresh `sonar run --trace` recorded by
 * capture/record-casts.mjs, not the frozen demo. The status strip (Main.tsx)
 * flips to amber and starts counting `POST /v1/run ×N` the moment this beat
 * starts; nothing in this file reads a number.
 */
import React from "react";
import { AbsoluteFill } from "remotion";
import { TerminalCast } from "../components/TerminalCast";

export const SceneLiveTrace: React.FC = () => (
  <AbsoluteFill style={{ padding: "0 140px", justifyContent: "center" }}>
    <TerminalCast src="run_trace" speed={1.8} rows={20} />
  </AbsoluteFill>
);
