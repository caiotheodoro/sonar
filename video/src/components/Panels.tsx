/**
 * Shared content panels.
 *
 * `Quote` keeps an honest distinction the rest of the pipeline enforces
 * automatically: most figures on screen are imported from results/demo, but a
 * few facts live only as prose in the repo (the incumbent's page, a decision
 * entry). Those are shown as quotations with a file citation rather than
 * dressed up as computed data.
 */
import React from "react";
import { interpolate, useCurrentFrame } from "remotion";
import { SERIES, T } from "../theme";

const rise = (frame: number, at: number) =>
  interpolate(frame, [at, at + 16], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

/** A fact that exists only as prose in the repo, shown as a citation. */
export const Quote: React.FC<{
  children: React.ReactNode;
  cite: string;
  at?: number;
}> = ({ children, cite, at = 0 }) => {
  const o = rise(useCurrentFrame(), at);
  return (
    <div style={{ opacity: o, transform: `translateY(${(1 - o) * 12}px)`, maxWidth: 1300 }}>
      <div
        style={{
          borderLeft: `3px solid ${T.accent}`,
          paddingLeft: 26,
          fontFamily: T.font,
          fontSize: 34,
          lineHeight: 1.4,
          color: T.text,
        }}
      >
        {children}
      </div>
      <div
        style={{ marginTop: 14, marginLeft: 29, fontFamily: T.mono, fontSize: 19, color: T.textMuted }}
      >
        {cite}
      </div>
    </div>
  );
};

/** A plain enumerated list, for run lists and citation footnotes. */
export const Checklist: React.FC<{
  items: string[];
  at?: number;
  columns?: number;
  accentIndex?: number;
}> = ({ items, at = 0, columns = 1, accentIndex = -1 }) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: `repeat(${columns}, 1fr)`,
        columnGap: 60,
        rowGap: 4,
      }}
    >
      {items.map((it, i) => {
        const o = rise(frame, at + i * 5);
        const hot = i === accentIndex;
        return (
          <div
            key={it}
            style={{
              display: "flex",
              gap: 18,
              alignItems: "baseline",
              padding: "10px 0",
              borderBottom: `1px solid ${T.border}`,
              opacity: o,
              transform: `translateY(${(1 - o) * 8}px)`,
            }}
          >
            <span style={{ fontFamily: T.mono, fontSize: 20, color: hot ? T.accent : T.textFaint }}>
              {String(i + 1).padStart(2, "0")}
            </span>
            <span
              style={{
                fontFamily: T.font,
                fontSize: 27,
                color: hot ? T.text : T.textMuted,
                fontWeight: hot ? 600 : 400,
              }}
            >
              {it}
            </span>
          </div>
        );
      })}
    </div>
  );
};

export { SERIES };
