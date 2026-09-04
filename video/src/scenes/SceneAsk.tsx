/**
 * Beat 4: reports what it can, abstains from what it can't, then answers.
 * Share of voice and sentiment arrive as one static group (no per-row
 * ceremony) — except PicPay, which takes the read-line's animated abstain
 * gesture, the same gesture a cleared value gets, resolving to a grey dash.
 * Then `sonar ask`, replayed from public/casts/ask.cast, with citations
 * docking to the real mention URLs the digest names.
 */
import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { ReadLine } from "../components/ReadLine";
import { TerminalCast } from "../components/TerminalCast";
import { pct, net } from "../data/results";
import { RESULTS, cueFrame } from "../manifest";
import { SENTIMENT, T } from "../theme";

const { shareOfVoice, sentiment } = RESULTS.stats;
const { topMentions, coverageGaps } = RESULTS.digest;

const sovRows = shareOfVoice.filter((r) => r.share !== null);
const picPay = shareOfVoice.find((r) => r.share === null);
const sentByBrand = new Map(sentiment.map((r) => [r.brand, r]));

const STATIC_AT = 0;

const Group: React.FC<{ children: React.ReactNode; at: number }> = ({ children, at }) => {
  const frame = useCurrentFrame();
  const o = interpolate(frame, [at, at + 14], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  return <div style={{ opacity: o, transform: `translateY(${(1 - o) * 10}px)` }}>{children}</div>;
};

export const SceneAsk: React.FC = () => (
  <AbsoluteFill style={{ padding: "0 140px", justifyContent: "center" }}>
    <Group at={STATIC_AT}>
      <div style={{ display: "flex", gap: 56 }}>
        {sovRows.map((r) => {
          const s = sentByBrand.get(r.brand);
          return (
            <div key={r.brand} style={{ minWidth: 220 }}>
              <div style={{ fontFamily: T.font, fontSize: 22, color: T.textMuted }}>{r.brand}</div>
              <div style={{ fontFamily: T.mono, fontSize: 52, fontWeight: 700, color: T.text, marginTop: 6 }}>
                {pct(r.share as number)}
              </div>
              <div style={{ fontFamily: T.mono, fontSize: 18, color: T.textFaint, marginTop: 4 }}>
                {r.ci95 ? `[${pct(r.ci95[0])}, ${pct(r.ci95[1])}]` : ""}
              </div>
              {s && s.net !== null ? (
                <div
                  style={{
                    fontFamily: T.mono,
                    fontSize: 22,
                    marginTop: 10,
                    color: s.net >= 0 ? SENTIMENT.pos : SENTIMENT.neg,
                  }}
                >
                  {net(s.net)} net
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </Group>

    {picPay ? (
      <div style={{ marginTop: 44 }}>
        <ReadLine
          label={`${picPay.brand}, share of voice`}
          value={null}
          domain={[0, 0.5]}
          format={pct}
          startFrame={cueFrame("ask", 1)}
          width={700}
        />
      </div>
    ) : null}

    <div style={{ marginTop: 48 }}>
      <TerminalCast src="ask" speed={1.6} rows={14} startFrame={cueFrame("ask", 2)} />
    </div>

    <Group at={cueFrame("ask", 2) + 40}>
      <div style={{ display: "flex", gap: 24, marginTop: 22, fontFamily: T.mono, fontSize: 18 }}>
        {topMentions.slice(0, 2).map((m, i) => (
          <a
            key={m.mentionId}
            href={m.url ?? undefined}
            style={{
              color: T.accent,
              border: `1px solid ${T.border}`,
              borderRadius: 6,
              padding: "4px 10px",
              textDecoration: "none",
            }}
          >
            [{i + 1}] {m.source}
          </a>
        ))}
        {coverageGaps[0] ? (
          <span
            style={{
              color: T.textFaint,
              border: `1px solid ${T.border}`,
              borderRadius: 6,
              padding: "4px 10px",
            }}
          >
            X/Twitter — {coverageGaps[0].reason}
          </span>
        ) : null}
      </div>
    </Group>
  </AbsoluteFill>
);
