/**
 * The signature. Every measured number in the video arrives the same way: an
 * amber line draws left-to-right and stops at the value on a fixed axis, the
 * figure counts up, and the 95% interval snaps in as `[ ]` brackets.
 *
 * A number sonar refused to guess takes the same gesture and resolves to a
 * single grey em-dash — same motion, different outcome. Never red; an
 * abstention is not an error.
 *
 * Frames are scene-local; `startFrame` is the frame within the scene at which
 * the gesture begins.
 */
import React from "react";
import { Easing, interpolate, useCurrentFrame } from "remotion";
import { MOTION, T } from "../theme";

const CURVE = Easing.bezier(MOTION.snap[0], MOTION.snap[1], MOTION.snap[2], MOTION.snap[3]);

export interface ReadLineProps {
  label: string;
  value: number | null;
  domain: [number, number];
  format: (n: number) => string;
  ci?: [number, number] | null;
  startFrame: number;
  width?: number;
  abstainNote?: string;
  emphasis?: boolean;
  /** A static reference tick on the same domain (e.g. the acceptance bar an audit is judged against). */
  mark?: { value: number; label: string };
}

const ease = (f: number, a: number, b: number, from: number, to: number): number =>
  interpolate(f, [a, b], [from, to], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: CURVE,
  });

export const ReadLine: React.FC<ReadLineProps> = ({
  label,
  value,
  domain,
  format,
  ci = null,
  startFrame,
  width = 900,
  abstainNote = "not enough data",
  emphasis = false,
  mark,
}) => {
  const f = Math.max(0, useCurrentFrame() - startFrame);
  const [lo, hi] = domain;
  const span = hi - lo || 1;
  const x = (v: number): number => ((v - lo) / span) * width;
  const abstained = value === null;

  const baseline = 70; // y of the line inside the svg
  const svgH = 96;

  // line geometry
  const originX = Math.max(2, x(lo));
  const fullX = x(hi);
  const targetX = abstained ? fullX : x(value as number);

  let lineX2: number;
  if (!abstained) {
    lineX2 = ease(f, 0, 10, originX, targetX);
  } else {
    // draw full, then retract to a stub
    const drawn = ease(f, 0, 10, originX, fullX);
    const retract = ease(f, 10, 18, drawn, originX + 26);
    lineX2 = f < 10 ? drawn : retract;
  }

  const dotOpacity = abstained ? ease(f, 8, 14, 1, 0) : ease(f, 0, 6, 0, 1) * ease(f, 40, 60, 1, 1);

  // value count-up
  const shown = abstained ? 0 : ease(f, 6, 16, lo, value as number);
  const valueOpacity = abstained ? 0 : ease(f, 6, 12, 0, 1);

  // abstain dash
  const dashOpacity = abstained ? ease(f, 12, 20, 0, 1) : 0;

  // ci brackets
  const ciOpacity = ci && !abstained ? ease(f, 14, 22, 0, 1) : 0;
  const ciShift = ci && !abstained ? ease(f, 14, 22, 10, 0) : 0;
  const ciLo = ci ? x(ci[0]) : 0;
  const ciHi = ci ? x(ci[1]) : 0;

  return (
    <div style={{ width, fontFamily: T.mono }}>
      <div style={{ fontFamily: T.font, fontSize: 21, color: T.textMuted, marginBottom: 10 }}>
        {label}
      </div>

      <div style={{ position: "relative", height: svgH }}>
        <svg width={width} height={svgH} style={{ position: "absolute", inset: 0 }}>
          {ci && !abstained ? (
            <g opacity={ciOpacity} transform={`translate(0, ${ciShift})`}>
              <line x1={ciLo} y1={baseline} x2={ciHi} y2={baseline} stroke={T.border} strokeWidth={1} />
              <text x={ciLo - 6} y={baseline + 8} fill={T.textFaint} fontSize={26} textAnchor="end">
                [
              </text>
              <text x={ciHi + 6} y={baseline + 8} fill={T.textFaint} fontSize={26}>
                ]
              </text>
            </g>
          ) : null}

          <line
            x1={originX}
            y1={baseline}
            x2={lineX2}
            y2={baseline}
            stroke={abstained ? T.abstain : T.accent}
            strokeWidth={2.5}
            strokeLinecap="round"
          />
          <circle cx={lineX2} cy={baseline} r={3.5} fill={abstained ? T.abstain : T.accent} opacity={dotOpacity} />

          {mark ? (
            <g>
              <line
                x1={x(mark.value)}
                y1={baseline - 14}
                x2={x(mark.value)}
                y2={baseline + 5}
                stroke={T.textFaint}
                strokeWidth={1.5}
              />
              <text x={x(mark.value)} y={baseline - 20} fill={T.textFaint} fontSize={17} textAnchor="middle">
                {mark.label}
              </text>
            </g>
          ) : null}
        </svg>

        {!abstained ? (
          <div
            style={{
              position: "absolute",
              left: Math.min(targetX + 20, width - 260),
              top: -12,
              fontSize: 96,
              fontWeight: 700,
              lineHeight: 1,
              color: emphasis ? T.accent : T.text,
              opacity: valueOpacity,
            }}
          >
            {format(shown)}
          </div>
        ) : (
          <>
            <div
              style={{
                position: "absolute",
                left: originX + 40,
                top: -18,
                fontSize: 96,
                fontWeight: 700,
                lineHeight: 1,
                color: T.abstain,
                opacity: dashOpacity,
              }}
            >
              &#8212;
            </div>
            <div
              style={{
                position: "absolute",
                left: originX + 40,
                top: 84,
                fontFamily: T.font,
                fontSize: 26,
                color: T.textFaint,
                opacity: dashOpacity,
              }}
            >
              {abstainNote}
            </div>
          </>
        )}
      </div>
    </div>
  );
};
