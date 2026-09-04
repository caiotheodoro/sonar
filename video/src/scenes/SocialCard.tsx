/**
 * The share card: a static 1200×630 receipt, for the X post and any link
 * preview. Same numbers as beat 1 and the receipt beat, same rule — nothing
 * here is typed, everything comes through RESULTS.
 */
import React from "react";
import { AbsoluteFill } from "remotion";
import { fmt, usd, usdWhole } from "../data/results";
import { PUBLISHED, RESULTS } from "../manifest";
import { T } from "../theme";

const { incumbent, totals, comparison } = RESULTS.receipt;

export const SocialCard: React.FC = () => (
  <AbsoluteFill style={{ backgroundColor: T.bg, fontFamily: T.font, color: T.text }}>
    <AbsoluteFill
      style={{
        backgroundImage: `linear-gradient(90deg, rgba(242,168,59,0.05) 1px, transparent 1px)`,
        backgroundSize: `48px 100%`,
      }}
    />
    <AbsoluteFill style={{ padding: "64px 72px", justifyContent: "space-between" }}>
      <div style={{ fontFamily: T.mono, fontSize: 22, color: T.textMuted }}>
        sonar · pay-per-call brand listening
      </div>

      <div style={{ display: "flex", alignItems: "baseline", gap: 56 }}>
        <div>
          <div style={{ fontFamily: T.mono, fontSize: 20, color: T.textFaint }}>
            {incumbent.name}, per month
          </div>
          <div
            style={{
              fontFamily: T.mono,
              fontSize: 88,
              fontWeight: 700,
              color: T.textFaint,
              letterSpacing: "-0.02em",
            }}
          >
            {usdWhole(incumbent.priceUsdMonth)}
          </div>
        </div>
        <div style={{ fontFamily: T.mono, fontSize: 48, color: T.textFaint }}>→</div>
        <div>
          <div style={{ fontFamily: T.mono, fontSize: 20, color: T.textMuted }}>
            one full brief, measured
          </div>
          <div
            style={{
              fontFamily: T.mono,
              fontSize: 96,
              fontWeight: 700,
              color: T.accent,
              letterSpacing: "-0.02em",
            }}
          >
            {usd(totals.totalUsd)}
          </div>
        </div>
      </div>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
        <div style={{ fontFamily: T.mono, fontSize: 22, color: T.textMuted }}>
          {comparison.ratio !== null ? `${fmt(comparison.ratio)}× cheaper at four briefs a month` : ""}
        </div>
        <div style={{ display: "flex", gap: 28, fontFamily: T.mono, fontSize: 24 }}>
          <span style={{ color: T.text }}>{PUBLISHED.code}</span>
          <span style={{ color: T.accent }}>{PUBLISHED.hashtag}</span>
        </div>
      </div>
    </AbsoluteFill>
  </AbsoluteFill>
);
