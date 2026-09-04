/** The repository and the hashtag. */
import React from "react";
import { PUBLISHED, RESULTS } from "../manifest";
import { displayFamily } from "../fonts";
import { T, TYPE } from "../theme";
import { Card, useSince, type CardProps } from "./Card";

const { sessionId, verdict } = RESULTS.receipt;

export const Outro: React.FC<CardProps> = () => {
  const f = useSince(0);
  return (
    <Card plate={["SONAR", "OPEN SOURCE"]} source={[sessionId, verdict]}>
      <div style={{ fontFamily: displayFamily, fontWeight: 900, fontSize: 300, lineHeight: 0.85, color: T.plate, textTransform: "uppercase" }}>
        The receipt
        <br />
        is the product.
      </div>
      <div style={{ marginTop: 56, display: "flex", gap: 64, alignItems: "baseline", opacity: f >= 12 ? 1 : 0 }}>
        <span style={{ fontFamily: T.mono, fontSize: TYPE.value, color: T.plate }}>{PUBLISHED.code}</span>
        <span style={{ fontFamily: T.mono, fontWeight: 700, fontSize: TYPE.value, color: T.signal }}>{PUBLISHED.hashtag}</span>
      </div>
    </Card>
  );
};
