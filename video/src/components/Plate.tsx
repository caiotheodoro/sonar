/**
 * A nameplate line: mono caps, segments separated by a slash, the first
 * segment in plate-white and the rest engraved grey. Optionally typed out
 * character by character (the robot is writing the label).
 */
import React from "react";
import { useCurrentFrame } from "remotion";
import { T, TYPE } from "../theme";

export const Plate: React.FC<{
  segments: string[];
  size?: number;
  typewriter?: boolean;
  /** Frames per character when typing. */
  cps?: number;
  startFrame?: number;
  style?: React.CSSProperties;
}> = ({ segments, size = TYPE.label, typewriter = false, cps = 0.6, startFrame = 0, style }) => {
  const frame = useCurrentFrame() - startFrame;
  const full = segments.join("  /  ");
  const shown = typewriter ? Math.max(0, Math.min(full.length, Math.floor(frame / cps))) : full.length;
  let consumed = 0;
  return (
    <div
      style={{
        fontFamily: T.mono,
        fontSize: size,
        letterSpacing: "0.08em",
        textTransform: "uppercase",
        whiteSpace: "pre",
        lineHeight: 1,
        ...style,
      }}
    >
      {segments.map((seg, i) => {
        const sep = i > 0 ? "  /  " : "";
        const sepStart = consumed;
        const segStart = sepStart + sep.length;
        consumed = segStart + seg.length;
        const sepShown = sep.slice(0, Math.max(0, Math.min(sep.length, shown - sepStart)));
        const segShown = seg.slice(0, Math.max(0, Math.min(seg.length, shown - segStart)));
        return (
          <React.Fragment key={i}>
            <span style={{ color: T.textFaint }}>{sepShown}</span>
            <span style={{ color: i === 0 ? T.plate : T.engrave }}>{segShown}</span>
          </React.Fragment>
        );
      })}
      {typewriter && shown < full.length ? <span style={{ color: T.signal }}>▌</span> : null}
    </div>
  );
};
